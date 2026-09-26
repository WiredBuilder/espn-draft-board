"""League-specific value model. Transparent: points = sum(projected stat x league points).
Value over replacement (VOR) = player points - points of the best player who would go undrafted
at that roster slot: teams x (starters + that slot's share of the bench). Bench seats are spread across
F, D and G in proportion to starters, so a 3-bench league drafts 39 players deeper than a no-bench one."""
import json

FWD = {"C", "LW", "RW"}
RATE_STATS = {10: "GAA", 11: "SV%"}  # per-game rates cannot be summed as points; skipped and reported


def slot_of(pos):
    return "F" if pos in FWD else pos


def roster_shape(raw):
    """ESPN lineupSlotCounts -> starters per model slot (F, D, G), bench count, IR count.
    C, LW, RW and UTIL all count as F starters; UTIL is almost always filled by a forward."""
    starters = {"F": 0, "D": 0, "G": 0}
    for name, n in raw.items():
        if name in ("C", "LW", "RW", "F", "UTIL"):
            starters["F"] += n
        elif name in ("D", "G"):
            starters[name] += n
    return starters, raw.get("BE", 0), raw.get("IR", 0)


def with_bench(starters, bench):
    """Spread bench seats across slots by largest-remainder on starter share; the sum is exact."""
    total = sum(starters.values()) or 1
    depth = dict(starters)
    for _ in range(bench):
        slot = max(depth, key=lambda k: starters[k] / total - (depth[k] - starters[k]) / max(bench, 1) if starters[k] else -1)
        depth[slot] += 1
    return depth


def describe(meta, stat_names):
    """The rules the board is running on, in one block, so a wrong league id or stale cookie is obvious."""
    st = meta["starters"]
    lines = [f"League: {meta['teams']} teams | starters F{st['F']} D{st['D']} G{st['G']} | bench {meta['bench']} | IR {meta['ir']}"]
    lines.append("Scoring: " + ", ".join(f"{stat_names.get(k, k)} {v:g}" for k, v in sorted(meta["scoring"].items()) if k not in RATE_STATS))
    if meta["rate_ignored"]:
        lines.append("Ignored (rate stats cannot be summed): " + ", ".join(meta["rate_ignored"]))
    d = meta["slots"]
    lines.append(f"Replacement level (teams x depth F{d['F']} D{d['D']} G{d['G']}): F {meta['repl']['F']:.0f}, D {meta['repl']['D']:.0f}, G {meta['repl']['G']:.0f}")
    return lines


def check(meta):
    """Refuse to run on an empty or half-loaded league rather than print a board that looks right."""
    problems = []
    if not meta["teams"]:
        problems.append("team count is 0")
    if not meta["scoring"]:
        problems.append("no scoring rules")
    if not sum(meta["starters"].values()):
        problems.append("no roster slots")
    if problems:
        raise SystemExit("League settings incomplete: " + "; ".join(problems) + ". Check ESPN_LEAGUE_ID and the cookies in .env, then run scripts/refresh.py.")


def latest(con, source, endpoint):
    return con.execute("SELECT run_id, retrieved_at FROM fetch_runs WHERE source_id=? AND endpoint=? AND ok=1 "
                       "ORDER BY run_id DESC LIMIT 1", (source, endpoint)).fetchone()


def build(con, season=2027):
    lg = latest(con, "espn_league", "league")
    pl = latest(con, "espn_league", "players")
    if lg is None or pl is None:
        raise SystemExit("League settings not loaded: no successful league pull in the database. For a private league run "
                         "scripts/set_login.py, then scripts/refresh.py. For an ESPN-default-scoring preview without login, "
                         "run scripts/board.py.")
    scoring = {r["stat_id"]: r["points"] for r in con.execute("SELECT * FROM league_scoring WHERE run_id=?", (lg["run_id"],))}
    raw_slots = {r["slot_name"]: r["count"] for r in con.execute(
        "SELECT * FROM league_roster_slots WHERE run_id=? AND count>0", (lg["run_id"],))}
    starters, bench, ir = roster_shape(raw_slots)
    slots = {k: v for k, v in with_bench(starters, bench).items() if v > 0}
    teams = con.execute("SELECT team_count FROM league_snapshots WHERE run_id=?", (lg["run_id"],)).fetchone()[0]
    rate_ignored = [RATE_STATS[k] for k in scoring if k in RATE_STATS]
    scoring = {k: v for k, v in scoring.items() if k not in RATE_STATS}
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
    meta = dict(scoring=scoring, slots=slots, starters=starters, bench=bench, ir=ir, rate_ignored=rate_ignored,
                teams=teams, repl=repl, league_pulled=lg["retrieved_at"], players_pulled=pl["retrieved_at"])
    return players, meta


def vona(avail, picks_until_next, need, modes=None, plan=None, already=None):
    """Value Over Next Available: how much you lose at this position if you wait.
    plan: list of (pick_no, owner_model, mode) for each intervening pick; see owners.simulate. When given,
    each owner is walked with their own habits (favourite players, first-goalie and first-D timing) and the
    simulated picks are returned as the third value. Without it, others draft by ESPN ADP, or by ESPN rank
    for owners flagged "rank" in modes (mostly autopick)."""
    log = []
    if plan:
        from fhdb import owners
        gone, log = owners.simulate(avail, plan, already)
    elif modes:
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
    return sorted(avail, key=lambda x: x["vona"], reverse=True), nxt, log
