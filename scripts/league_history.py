"""Pull completed drafts for your league from past seasons into draft_history (read-only).
  .venv/bin/python scripts/league_history.py                 # seasons 2023..2026 (draft nights Oct 2022..Oct 2025)
  .venv/bin/python scripts/league_history.py --seasons 2026
"""
import argparse, hashlib, json, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fhdb import db, espn
from espn_api.requests.espn_requests import EspnFantasyRequests

FWD = {"C", "LW", "RW"}
ap = argparse.ArgumentParser(); ap.add_argument("--seasons", default="2023,2024,2025,2026")
a = ap.parse_args()
espn.load_env(); con = db.connect()
league = int(os.environ["ESPN_LEAGUE_ID"]); ck = espn.cookies()


def okey(member_id):
    return hashlib.sha1((member_id or "").encode()).hexdigest()[:8] if member_id else None


for season in [int(x) for x in a.seasons.split(",")]:
    req = EspnFantasyRequests(sport="nhl", year=season, league_id=league, cookies=ck)
    run = db.start_run(con, "espn_league_history", "draft", season)
    try:
        d = req.league_get(params={"view": ["mDraftDetail", "mTeam", "mSettings"]})
    except Exception as e:
        db.finish_run(con, run, False, None, 0, type(e).__name__); print(season, "failed:", type(e).__name__); continue
    picks = d.get("draftDetail", {}).get("picks", [])
    # Same format as espn.refresh_league (first last, then display name) so owners join to fantasy_teams.owner_names.
    members = {m["id"]: (f'{m.get("firstName", "")} {m.get("lastName", "")}'.strip() or m.get("displayName") or "?") for m in d.get("members", [])}
    teams = {}
    for t in d.get("teams", []):
        owners = t.get("owners") or []
        teams[t["id"]] = (t.get("name") or f'{t.get("location","")} {t.get("nickname","")}'.strip(),
                          okey(owners[0]) if owners else None, members.get(owners[0], "?") if owners else "?")
    ids = sorted({p["playerId"] for p in picks if (p.get("playerId") or 0) > 0})
    # ESPN returns HTTP 400 for filterIds on this view; pull that season's pool (no active filter, so retired players appear) and map by id.
    flt = {"players": {"limit": 2500, "sortDraftRanks": {"sortPriority": 100, "sortAsc": True, "value": "STANDARD"},
                       "filterStatsForTopScoringPeriodIds": {"value": 1, "additionalValue": [f"00{season}"]}}}
    pinfo = {}
    try:
        pd = req.league_get(params={"view": "kona_player_info"}, headers={"x-fantasy-filter": json.dumps(flt)})
        for e in pd.get("players", []):
            p = e.get("player") or {}
            rk = ((p.get("draftRanksByRankType") or {}).get("STANDARD") or {}).get("rank")
            own = p.get("ownership") or {}
            st = next((s for s in p.get("stats", []) if s.get("id") == f"00{season}"), {})
            pinfo[p["id"]] = (p.get("fullName"), p.get("defaultPositionId"), rk, own.get("averageDraftPosition"),
                              st.get("appliedTotal"), float((st.get("stats") or {}).get("34", 0) or 0))
    except Exception as e:
        print(season, "player info failed:", type(e).__name__)
    POS = {1: "C", 2: "LW", 3: "RW", 4: "D", 5: "G"}
    n = 0
    for pk in picks:
        pid = pk.get("playerId") or -1
        if pid <= 0:
            continue
        name, posid, rk, adp, pts, gp = pinfo.get(pid, (None, None, None, None, None, None))
        pos = POS.get(posid)
        tname, ok_, oname = teams.get(pk.get("teamId"), ("?", None, "?"))
        con.execute("INSERT OR REPLACE INTO draft_history VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (season, pk.get("overallPickNumber"), run, pk.get("roundId"), pk.get("roundPickNumber"), pk.get("teamId"), tname,
                     ok_, oname, pid, name, pos, ("F" if pos in FWD else pos), pk.get("autoDraftTypeId"), rk, adp, pts, gp))
        n += 1
    db.finish_run(con, run, True, 200, n)
    missing = sum(1 for pk in picks if (pk.get("playerId") or 0) > 0 and pk["playerId"] not in pinfo)
    print(f"{season}: {n} picks stored, {len(teams)} teams, player info missing for {missing}")
