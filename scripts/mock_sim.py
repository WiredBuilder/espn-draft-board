"""Simulate a mock draft where the other teams auto-pick by ESPN rank (how ESPN AUTO works).
  .venv/bin/python scripts/mock_sim.py --slot 4 --taken "Draisaitl" --mine "Leon Draisaitl"
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fhdb import db, rank
ap = argparse.ArgumentParser(); ap.add_argument("--slot", type=int, default=4); ap.add_argument("--teams", type=int, default=13)
ap.add_argument("--mine", default="", help="comma list of players you already took (in order)")
ap.add_argument("--upto", type=int, default=100)
a = ap.parse_args()
con = db.connect(); P, m = rank.build(con)
T = a.teams
order = []
for r in range(1, 21): order += list(range(1, T + 1)) if r % 2 else list(range(T, 0, -1))
mine_pos = [i for i, s in enumerate(order, 1) if s == a.slot]
forced = [n.strip().lower() for n in a.mine.split(",") if n.strip()]
taken, need = set(), dict(m["slots"])
by_rank = sorted([x for x in P if x["espn_rank"]], key=lambda x: x["espn_rank"])
k = 0
for i, s in enumerate(order[:a.upto], 1):
    if s == a.slot:
        j = mine_pos.index(i); gap = mine_pos[j + 1] - i - 1 if j + 1 < len(mine_pos) else 0
        avail = [dict(x) for x in P if x["espn_id"] not in taken and need[x["slot"]] > 0]
        avail_r = sorted(avail, key=lambda x: x["espn_rank"] or 9999)
        gone = {x["espn_id"] for x in avail_r[:gap]}
        nxt = {sl: max([x["vor"] for x in avail if x["slot"] == sl and x["espn_id"] not in gone] or [0]) for sl in need}
        for x in avail: x["vona"] = x["vor"] - nxt[x["slot"]]
        avail.sort(key=lambda x: x["vona"], reverse=True)
        if k < len(forced):
            pick = next(x for x in P if x["full_name"].lower() == forced[k]); tag = "you took"
        else:
            pick = avail[0]; tag = "RECOMMEND"
        alt = next(x for x in avail if x["espn_id"] != pick["espn_id"])
        print(f"Pick {i}: {tag} {pick['full_name']} ({pick['slot']} {pick['team']}, {pick['pts']:.0f} pts, VOR {pick['vor']:.0f}) | backup {alt['full_name']} ({alt['slot']}, {alt['pts']:.0f})")
        taken.add(pick["espn_id"]); need[pick["slot"]] -= 1; k += 1
    else:
        x = next(x for x in by_rank if x["espn_id"] not in taken); taken.add(x["espn_id"])
