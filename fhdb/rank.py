"""League-specific value model. Transparent: points = sum(projected stat x league points).
Value over replacement (VOR) = player points - points of the best player who would go undrafted
at that roster slot (13 teams x starters per slot). No bench in this league, so every pick starts."""
import json

FWD = {"C", "LW", "RW"}


def slot_of(pos):
    return "F" if pos in FWD else pos


def latest(con, source, endpoint):
    return con.execute("SELECT run_id, retrieved_at FROM fetch_runs WHERE source_id=? AND endpoint=? AND ok=1 "
                       "ORDER BY run_id DESC LIMIT 1", (source, endpoint)).fetchone()


def build(con, season=2027):
    lg = latest(con, "espn_league", "league")
    pl = latest(con, "espn_league", "players")
    scoring = {r["stat_id"]: r["points"] for r in con.execute("SELECT * FROM league_scoring WHERE run_id=?", (lg["run_id"],))}
    slots = {r["slot_name"]: r["count"] for r in con.execute(
        "SELECT * FROM league_roster_slots WHERE run_id=? AND count>0", (lg["run_id"],))}
    teams = con.execute("SELECT team_count FROM league_snapshots WHERE run_id=?", (lg["run_id"],)).fetchone()[0]
    rows = con.execute(f"""
      SELECT p.espn_id, p.full_name, p.default_position pos, t.abbrev team, s.espn_rank, s.adp, s.injury_status,
             s.on_team_id, s.last_news_at, pr.stats_json proj, pr.applied_total espn_pts, la.stats_json last
      FROM player_snapshots s JOIN players p USING (espn_id)
      LEFT JOIN pro_teams t ON t.pro_team_id = s.pro_team_id
      LEFT JOIN stat_lines pr ON pr.run_id=s.run_id AND pr.espn_id=s.espn_id AND pr.split_code='10{season}'
      LEFT JOIN stat_lines la ON la.run_id=s.run_id AND la.espn_id=s.espn_id AND la.split_code='00{season-1}'
      WHERE s.run_id=?""", (pl["run_id"],)).fetchall()

    def pts(js):
        st = json.loads(js) if js else None
        if not st:
            return None, {}
        return sum(float(st.get(str(k), 0)) * v for k, v in scoring.items()), st

    players = []
    for r in rows:
        p, st = pts(r["proj"])
        lp, lst = pts(r["last"])
        basis = "2027 ESPN projection" if p is not None else ("2026 actual (no projection)" if lp is not None else None)
        if basis is None:
            continue
        gp = float((st or lst).get("34", 0) or 0)
        players.append(dict(r) | {"slot": slot_of(r["pos"]), "pts": p if p is not None else lp, "basis": basis,
                                  "last_pts": lp, "gp": gp, "stats": st or lst})
    repl = {}
    for slot, n in slots.items():
        pool = sorted((x["pts"] for x in players if x["slot"] == slot), reverse=True)
        idx = teams * n
        repl[slot] = pool[idx] if len(pool) > idx else (pool[-1] if pool else 0)
    for x in players:
        x["vor"] = x["pts"] - repl.get(x["slot"], 0)
        x["risk"] = []
        if x["injury_status"] not in (None, "ACTIVE"):
            x["risk"].append(x["injury_status"])
        if x["basis"].startswith("2026"):
            x["risk"].append("no 2027 projection")
    players.sort(key=lambda x: x["vor"], reverse=True)
    meta = dict(scoring=scoring, slots=slots, teams=teams, repl=repl, league_pulled=lg["retrieved_at"],
                players_pulled=pl["retrieved_at"])
    return players, meta


def vona(avail, picks_until_next, need, modes=None):
    """Value Over Next Available: how much you lose at this position if you wait.
    Assumes other teams draft by ESPN ADP until your next pick (an assumption, shown as such).
    modes: optional list, one entry per intervening pick, "adp" (human owner) or "rank" (owner who mostly
    autopicks, so ESPN drafts for them in ESPN rank order). Built from this league's draft history."""
    if modes:
        gone, left = set(), list(avail)
        for m in modes:
            key = (lambda x: x["espn_rank"] or 9999) if m == "rank" else (lambda x: x["adp"] or 999)
            pick = min(left, key=key, default=None)
            if pick is None:
                break
            gone.add(pick["espn_id"]); left.remove(pick)
    else:
        by_adp = sorted(avail, key=lambda x: x["adp"] or 999)
        gone = {x["espn_id"] for x in by_adp[:max(picks_until_next, 0)]}
    nxt = {}
    for slot in need:
        left = [x["vor"] for x in avail if x["slot"] == slot and x["espn_id"] not in gone]
        nxt[slot] = max(left) if left else 0
    for x in avail:
        x["vona"] = x["vor"] - nxt.get(x["slot"], 0)
        x["likely_gone"] = x["espn_id"] in gone
    return sorted(avail, key=lambda x: x["vona"], reverse=True), nxt
