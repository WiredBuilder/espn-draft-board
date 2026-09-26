"""League-specific draft board (read-only).
  .venv/bin/python scripts/draft_board.py            # use data already in the database
  .venv/bin/python scripts/draft_board.py --live     # re-pull league first (picks made so far)
  .venv/bin/python scripts/draft_board.py --watch 5  # re-pull every 5 s during the draft, Ctrl-C to stop
  .venv/bin/python scripts/draft_board.py --csv draft_board.csv --top 300
"""
import argparse, csv, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fhdb import db, espn, rank, owners

ap = argparse.ArgumentParser()
ap.add_argument("--live", action="store_true"); ap.add_argument("--top", type=int, default=25)
ap.add_argument("--csv"); ap.add_argument("--pos", choices=["F", "D", "G"])
ap.add_argument("--watch", type=float, metavar="SECONDS", help="re-pull and redraw every N seconds until the draft ends")
ap.add_argument("--taken-file", metavar="PATH", help="text file, one drafted player name per line, re-read every tick (fallback when the API shows no picks)")
ap.add_argument("--skip-file", metavar="PATH", help="text file, one player name per line, never recommended (injured, personal rule)")
a = ap.parse_args()
espn.load_env()
con = db.connect()
MODELS = owners.models(con)
LAYER2 = owners.summary(con, MODELS)


def refresh(players=True):
    espn.refresh_league(con, int(os.environ["ESPN_LEAGUE_ID"]), int(os.environ.get("ESPN_SEASON", 2027)),
                        None, int(os.environ["MY_TEAM_ID"]), players=players)


def render():
    """Print the board. Returns True when the draft is over."""
    P, m = rank.build(con)
    lg = rank.latest(con, "espn_league", "league")["run_id"]
    taken = {r[0] for r in con.execute("SELECT espn_id FROM draft_picks WHERE run_id=? AND espn_id > 0", (lg,))}
    taken |= {r[0] for r in con.execute("SELECT espn_id FROM roster_entries WHERE run_id=? AND espn_id > 0", (lg,))}
    manual, unmatched, manual_mine = 0, [], set()
    if a.taken_file and Path(a.taken_file).exists():
        by_name = {x["full_name"].lower(): x["espn_id"] for x in P}
        for line in Path(a.taken_file).read_text().splitlines():
            n = line.strip().lower()
            if not n or n.startswith("#"):
                continue
            mine_flag = n.startswith("*")  # "* Name" = my own pick
            n = n.lstrip("* ").strip()
            hit = by_name.get(n) or next((v for k, v in by_name.items() if n in k), None)
            if hit:
                taken.add(hit); manual += 1
                if mine_flag:
                    manual_mine.add(hit)
            else:
                unmatched.append(line.strip())
    me = con.execute("SELECT team_id, name, draft_position FROM fantasy_teams WHERE run_id=? AND is_mine=1", (lg,)).fetchone()
    # Our roster = our draft picks so far + roster view (the roster view can lag during a live draft).
    my_ids = {r[0] for r in con.execute("SELECT espn_id FROM draft_picks WHERE run_id=? AND team_id=? AND espn_id > 0", (lg, me["team_id"]))}
    my_ids |= {r[0] for r in con.execute("SELECT espn_id FROM roster_entries WHERE run_id=? AND team_id=? AND espn_id > 0", (lg, me["team_id"]))}
    my_ids |= manual_mine
    mine = [x for x in P if x["espn_id"] in my_ids]
    need = {s: n - sum(1 for x in mine if x["slot"] == s) for s, n in m["slots"].items()}
    skip = set()
    if a.skip_file and Path(a.skip_file).exists():
        by_name = {x["full_name"].lower(): x["espn_id"] for x in P}
        for line in Path(a.skip_file).read_text().splitlines():
            n = line.strip().lower()
            if n and not n.startswith("#"):
                hit = by_name.get(n) or next((v for k, v in by_name.items() if n in k), None)
                if hit:
                    skip.add(hit)
    avail = [x for x in P if x["espn_id"] not in taken and x["espn_id"] not in skip and need.get(x["slot"], 0) > 0 and (not a.pos or x["slot"] == a.pos)]

    T, pos = m["teams"], me["draft_position"]
    made = con.execute("SELECT COUNT(*) FROM draft_picks WHERE run_id=? AND espn_id > 0", (lg,)).fetchone()[0]
    made = max(made, len(taken))  # taken-file fallback: names typed by hand count as picks made
    total = T * sum(m["slots"].values())
    picks = [(r - 1) * T + (pos if r % 2 else T - pos + 1) for r in range(1, sum(m["slots"].values()) + 1)]
    nxt = [p for p in picks if p > made][:3]
    gap = (nxt[1] - nxt[0]) if len(nxt) > 1 else 0
    # Picks by others between now and your NEXT-after-this pick, each walked with that owner's own habits
    # (Layer 2: favourite players, first-goalie and first-D timing, autopick share). Owners with no history
    # draft by ADP; owners who mostly autopick (under 60% human) draft in ESPN rank order.
    slot_owner = {r[0]: r[1] for r in con.execute("SELECT draft_position, owner_names FROM fantasy_teams WHERE run_id=?", (lg,))}

    def owner_slot(p):
        r, i = (p - 1) // T + 1, (p - 1) % T + 1
        return i if r % 2 else T - i + 1

    between = [p for p in range(made + 1, nxt[1])] if len(nxt) > 1 else []
    between = [p for p in between if p != nxt[0]]
    plan = []
    for p in between:
        o = MODELS.get(slot_owner.get(owner_slot(p)))
        mode = "rank" if o and o["human_pct"] < 60 else "adp"
        plan.append((p, dict(o, name=slot_owner.get(owner_slot(p))) if o else None, mode))
    # Slots each owner has already filled this draft, so the simulation does not hand them a second first-goalie.
    slot_of_id = {x["espn_id"]: x["slot"] for x in P}
    already = {}
    for r in con.execute("SELECT t.owner_names, d.espn_id FROM draft_picks d JOIN fantasy_teams t ON t.run_id=d.run_id AND t.team_id=d.team_id WHERE d.run_id=? AND d.espn_id>0", (lg,)):
        if r[1] in slot_of_id:
            already.setdefault(r[0], set()).add(slot_of_id[r[1]])
    n_rank = sum(1 for _, _, mm in plan if mm == "rank")
    avail, next_av, sim = rank.vona(avail, len(between), need, plan=plan if MODELS else None,
                                    modes=[mm for _, _, mm in plan] if not MODELS else None, already=already)
    # Positional run alarm: how many of each slot the simulation expects to vanish before your next pick,
    # and what that costs you in VOR at that slot.
    alarms = []
    for slot in ("G", "D", "F"):
        n_sim = sum(1 for _, _, x, _ in sim if x["slot"] == slot)
        best_now = max((x["vor"] for x in avail if x["slot"] == slot), default=0)
        drop = best_now - next_av.get(slot, 0)
        if slot != "F" and n_sim >= 2 and drop >= 5 and need.get(slot, 0) > 0:
            alarms.append(f"{slot} run: {n_sim} {slot} likely gone before pick {nxt[1] if len(nxt) > 1 else '-'}, best {slot} VOR drops {drop:.0f}")

    on_clock = nxt and nxt[0] == made + 1
    print(f"{me['name']} | draft slot {pos} of {T} | your next picks: {nxt} | picks made so far: {made}/{total}"
          + ("   <<< YOU ARE ON THE CLOCK >>>" if on_clock else f"   ({nxt[0] - made - 1} picks until yours)" if nxt else ""))
    last = con.execute("""SELECT d.overall_pick, t.name, p.full_name FROM draft_picks d
        JOIN fantasy_teams t ON t.run_id=d.run_id AND t.team_id=d.team_id
        LEFT JOIN players p ON p.espn_id=d.espn_id
        WHERE d.run_id=? AND d.espn_id>0 ORDER BY d.overall_pick DESC LIMIT 3""", (lg,)).fetchall()
    if last:
        print("Last picks: " + " | ".join(f"#{r[0]} {r[1][:18]}: {r[2] or '?'}" for r in reversed(last)))
    print(f"Still needed: " + ", ".join(f"{k} {v}" for k, v in need.items()))
    if a.taken_file:
        print(f"Taken file: {manual} names removed" + (f" | NOT MATCHED: {', '.join(unmatched)}" if unmatched else ""))
    print(f"Scoring: your league (see refresh.py output). Replacement level F {m['repl']['F']:.0f}, D {m['repl']['D']:.0f}, G {m['repl']['G']:.0f}")
    print(f"Data pulled {m['players_pulled']} UTC. Projections: ESPN (single source).")
    print(LAYER2)
    for al in alarms:
        print(f"!!! {al}")
    print()
    if not avail:
        print("Nothing left to draft for your open slots.")
        return made >= total
    rec, alt = avail[0], (avail[1] if len(avail) > 1 else avail[0])
    print(f">>> PICK: {rec['full_name']} ({rec['slot']}, {rec['team']}) | backup: {alt['full_name']} ({alt['slot']}, {alt['team']})")
    print(f"    Waiting costs: F {next_av.get('F',0):.0f} / D {next_av.get('D',0):.0f} / G {next_av.get('G',0):.0f} VOR expected still there at pick {nxt[1] if len(nxt)>1 else '-'} ({len(between)} picks in between: {len(plan)-n_rank-sum(1 for _,o,_ in plan if o is None)} modelled owners, {n_rank} autopick-style, {sum(1 for _,o,_ in plan if o is None)} unknown by ADP)")
    if sim:
        print("    Expected before your next pick: " + ", ".join(f"{x['full_name'].split()[-1]} ({why})" for _, _, x, why in sim[:8]) + (" ..." if len(sim) > 8 else ""))
    print()
    print(f"{'#':>3} {'Player':24}{'Pos':4}{'Team':5}{'ADP':>6}{'Pts':>7}{'VOR':>6}{'VONA':>6}  Notes")
    for i, x in enumerate(avail[:a.top], 1):
        s = x["stats"]
        line = (f"W{float(s.get('1',0)):.0f} SO{float(s.get('7',0)):.0f}" if x["slot"] == "G"
                else f"G{float(s.get('13',0)):.0f} A{float(s.get('14',0)):.0f} PPG{float(s.get('18',0)):.0f}")
        print(f"{i:>3} {x['full_name'][:23]:24}{x['pos']:4}{(x['team'] or '?'):5}{(x['adp'] or 0):6.1f}{x['pts']:7.0f}{x['vor']:6.0f}{x['vona']:6.0f}  {line} {' '.join(x['risk'])}")
    if a.csv:
        with open(a.csv, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["rank", "player", "pos", "slot", "team", "adp", "proj_pts", "vor", "basis", "injury", "espn_rank", "data_pulled_utc"])
            for i, x in enumerate(avail[:a.top], 1):
                w.writerow([i, x["full_name"], x["pos"], x["slot"], x["team"], x["adp"], round(x["pts"], 1), round(x["vor"], 1),
                            x["basis"], x["injury_status"], x["espn_rank"], m["players_pulled"]])
        print(f"\nSaved {a.csv}")
    return made >= total


if a.watch:
    first = True  # full pull (players + picks) once, then picks only: keeps the database small during a 2-hour draft
    try:
        while True:
            t0 = time.time()
            try:
                refresh(players=first)
                first = False
                err = None
            except Exception as e:  # network blip or ESPN hiccup: show stale board, retry next tick
                err = f"{type(e).__name__} (showing last good data)"
            print("\033[2J\033[H", end="")  # clear screen
            done = render()
            print(f"\n[{time.strftime('%H:%M:%S')}] refresh took {time.time() - t0:.1f}s, next in {a.watch:g}s"
                  + (f" | REFRESH FAILED: {err}" if err else "") + " | Ctrl-C to stop")
            if done:
                print("Draft complete. Stopping.")
                break
            time.sleep(max(0.0, a.watch - (time.time() - t0)))
    except KeyboardInterrupt:
        print("\nStopped.")
else:
    if a.live:
        refresh()
    render()
