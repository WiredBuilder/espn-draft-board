"""ESPN source adapter (read-only). Uses the espn-api package's request layer for auth."""
import json
import os
from pathlib import Path

import requests

from espn_api.requests.espn_requests import EspnFantasyRequests, ESPNAccessDenied  # noqa: F401

from . import db

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fhl/seasons/"
POS = {1: "C", 2: "LW", 3: "RW", 4: "D", 5: "G"}
SLOTS = {0: "C", 1: "LW", 2: "RW", 3: "F", 4: "D", 5: "G", 6: "UTIL", 7: "BE", 8: "IR"}
SPLIT_LABEL = {"00": "actual_season", "01": "last_7", "02": "last_15", "03": "last_30", "10": "projection"}
UA = {"User-Agent": "fantasy-hockey-research/0.1 (personal, read-only)"}


def load_env(path=None):
    """Read .env into os.environ without printing anything."""
    p = Path(path or db.ROOT / ".env")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def cookies():
    s2, swid = os.environ.get("ESPN_S2"), os.environ.get("ESPN_SWID")
    if s2 and swid:
        return {"espn_s2": s2, "SWID": swid if swid.startswith("{") else "{" + swid + "}"}
    return None


def _player_filter(season, limit=2000):
    return {"players": {
        "filterActive": {"value": True},
        "limit": limit,
        "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "STANDARD"},
        "filterStatsForTopScoringPeriodIds": {"value": 2, "additionalValue": [
            f"00{season}", f"10{season}", f"00{season - 1}", f"01{season}", f"02{season}"]},
    }}


def _ms_to_iso(ms):
    if not ms:
        return None
    import datetime as dt
    return dt.datetime.fromtimestamp(ms / 1000, dt.timezone.utc).replace(microsecond=0).isoformat()


def save_players(con, run_id, players, source_id, scoring_basis):
    """Upsert identity, write snapshot + stat lines + injury changes. Returns count."""
    ts = db.now_utc()
    n = 0
    for entry in players:
        p = entry.get("player") or entry.get("playerPoolEntry", {}).get("player") or entry
        pid = p["id"]
        con.execute("""INSERT INTO players (espn_id, full_name, first_name, last_name, default_position,
                eligible_slots_json, pro_team_id, jersey, active, first_seen_run_id, updated_run_id)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(espn_id) DO UPDATE SET full_name=excluded.full_name, first_name=excluded.first_name,
                last_name=excluded.last_name, default_position=excluded.default_position,
                eligible_slots_json=excluded.eligible_slots_json, pro_team_id=excluded.pro_team_id,
                jersey=excluded.jersey, active=excluded.active, updated_run_id=excluded.updated_run_id""",
                    (pid, p.get("fullName"), p.get("firstName"), p.get("lastName"),
                     POS.get(p.get("defaultPositionId"), str(p.get("defaultPositionId"))),
                     json.dumps([SLOTS.get(s, s) for s in p.get("eligibleSlots", [])]),
                     p.get("proTeamId"), p.get("jersey"), 1 if p.get("active") else 0, run_id, run_id))
        rank = (p.get("draftRanksByRankType") or {}).get("STANDARD", {})
        own = p.get("ownership") or {}
        con.execute("""INSERT OR REPLACE INTO player_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (run_id, pid, p.get("proTeamId"), p.get("injuryStatus"), 1 if p.get("injured") else 0,
                     rank.get("rank"), rank.get("auctionValue"), own.get("averageDraftPosition"),
                     own.get("averageDraftPositionPercentChange"), own.get("auctionValueAverage"),
                     own.get("percentOwned"), own.get("percentStarted"), entry.get("onTeamId"),
                     entry.get("status"), _ms_to_iso(p.get("lastNewsDate")), p.get("seasonOutlook")))
        for s in p.get("stats", []):
            code = s.get("id", "")
            if code[:2] not in SPLIT_LABEL or not s.get("stats"):
                continue
            con.execute("INSERT OR REPLACE INTO stat_lines VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (run_id, pid, code, s.get("seasonId"), SPLIT_LABEL[code[:2]], s.get("statSourceId"),
                         scoring_basis, s.get("appliedTotal"), s.get("appliedAverage"), json.dumps(s["stats"])))
        status = p.get("injuryStatus")
        if status:
            last = con.execute("""SELECT status, first_seen_at FROM injury_history WHERE espn_id=? AND source_id=?
                                  ORDER BY first_seen_at DESC LIMIT 1""", (pid, source_id)).fetchone()
            if last and last["status"] == status:
                con.execute("UPDATE injury_history SET last_seen_at=? WHERE espn_id=? AND source_id=? AND first_seen_at=?",
                            (ts, pid, source_id, last["first_seen_at"]))
            else:
                con.execute("INSERT INTO injury_history VALUES (?,?,?,?,?,?)", (pid, source_id, status, ts, ts, run_id))
        n += 1
    return n


def refresh_public(con, season):
    """No login needed: full player pool with ESPN default-scoring projections, ADP, injuries."""
    run = db.start_run(con, "espn_public", "players", season)
    url = f"{BASE}{season}/segments/0/leaguedefaults/1"
    r = requests.get(url, params={"view": "kona_player_info"},
                     headers={**UA, "x-fantasy-filter": json.dumps(_player_filter(season))}, timeout=60)
    if r.status_code != 200:
        db.finish_run(con, run, False, r.status_code, 0, "public player pool failed")
        raise RuntimeError(f"ESPN public players HTTP {r.status_code}")
    n = save_players(con, run, r.json().get("players", []), "espn_public", "espn_default")
    db.finish_run(con, run, True, 200, n)

    run2 = db.start_run(con, "espn_public", "pro_teams", season)
    r = requests.get(f"{BASE}{season}", params={"view": "proTeamSchedules_wl"}, headers=UA, timeout=60)
    teams = r.json().get("settings", {}).get("proTeams", []) if r.status_code == 200 else []
    for t in teams:
        con.execute("INSERT OR REPLACE INTO pro_teams VALUES (?,?,?,?,?,?)",
                    (t["id"], t.get("abbrev"), t.get("location"), t.get("name"),
                     json.dumps(t.get("proGamesByScoringPeriod", {})), run2))
    db.finish_run(con, run2, r.status_code == 200, r.status_code, len(teams))
    return n, len(teams)


def refresh_league(con, league_id, season, my_team_name=None, my_team_id=None, players=True):
    """Private league read (needs ESPN_S2 + ESPN_SWID). Settings, teams, rosters, draft, league-scored players.
    players=False skips the 1500-player pull (used by the draft watch loop, which only needs fresh picks)."""
    ck = cookies()
    req = EspnFantasyRequests(sport="nhl", year=season, league_id=league_id, cookies=ck)
    run = db.start_run(con, "espn_league", "league", season)
    try:
        data = req.league_get(params={"view": ["mSettings", "mTeam", "mRoster", "mDraftDetail", "mStatus"]})
    except Exception as e:  # ESPNAccessDenied, 404, etc. Never echo cookies.
        db.finish_run(con, run, False, None, 0, type(e).__name__)
        raise
    s = data.get("settings", {})
    dd = data.get("draftDetail", {})
    con.execute("INSERT OR REPLACE INTO league_snapshots VALUES (?,?,?,?,?,?,?,?,?,?)",
                (run, league_id, data.get("seasonId"), s.get("name"), s.get("size"),
                 s.get("scoringSettings", {}).get("scoringType"), s.get("draftSettings", {}).get("type"),
                 _ms_to_iso(s.get("draftSettings", {}).get("date")), 1 if dd.get("drafted") else 0, json.dumps(s)))
    for item in s.get("scoringSettings", {}).get("scoringItems", []):
        con.execute("INSERT OR REPLACE INTO league_scoring VALUES (?,?,?,?)",
                    (run, item.get("statId"), item.get("points"), 1 if item.get("isReverseItem") else 0))
    for slot, cnt in (s.get("rosterSettings", {}).get("lineupSlotCounts", {}) or {}).items():
        con.execute("INSERT OR REPLACE INTO league_roster_slots VALUES (?,?,?,?)",
                    (run, int(slot), SLOTS.get(int(slot), slot), cnt))
    members = {m["id"]: f'{m.get("firstName", "")} {m.get("lastName", "")}'.strip() or m.get("displayName")
               for m in data.get("members", [])}
    order = s.get("draftSettings", {}).get("pickOrder", [])
    for t in data.get("teams", []):
        name = t.get("name") or f'{t.get("location", "")} {t.get("nickname", "")}'.strip()
        con.execute("INSERT OR REPLACE INTO fantasy_teams VALUES (?,?,?,?,?,?,?)",
                    (run, t["id"], t.get("abbrev"), name, ", ".join(members.get(o) or "?" for o in t.get("owners", [])),
                     order.index(t["id"]) + 1 if t["id"] in order else None,
                     1 if (my_team_id and t["id"] == my_team_id) or (my_team_name and name.strip().lower() == my_team_name.lower()) else 0))
        for e in t.get("roster", {}).get("entries", []):
            con.execute("INSERT OR REPLACE INTO roster_entries VALUES (?,?,?,?,?)",
                        (run, t["id"], e.get("playerId"), e.get("lineupSlotId"), e.get("acquisitionType")))
    for i, pk in enumerate(dd.get("picks", []), 1):
        con.execute("INSERT OR REPLACE INTO draft_picks VALUES (?,?,?,?,?,?,?)",
                    (run, pk.get("overallPickNumber", i), pk.get("roundId"), pk.get("roundPickNumber"),
                     pk.get("teamId"), pk.get("playerId"), 1 if pk.get("keeper") else 0))
    db.finish_run(con, run, True, 200, len(data.get("teams", [])))

    if not players:
        return run, 0
    # Players scored with THIS league's rules, plus who owns them.
    run2 = db.start_run(con, "espn_league", "players", season)
    pdata = req.league_get(params={"view": "kona_player_info"},
                           headers={"x-fantasy-filter": json.dumps(_player_filter(season, 1500))})
    n = save_players(con, run2, pdata.get("players", []), "espn_league", f"league_{league_id}")
    db.finish_run(con, run2, True, 200, n)
    return run, n
