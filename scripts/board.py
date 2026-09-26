"""Quick draft board from the latest data.
Usage: .venv/bin/python scripts/board.py [--pos C|LW|RW|D|G] [--top 40] [--csv out.csv]
Uses league-scored projections if a league refresh exists, otherwise ESPN default scoring (labelled).
Excludes players already on a fantasy roster when league data is available.
"""
import argparse, csv, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fhdb import db

ap = argparse.ArgumentParser()
ap.add_argument("--pos"); ap.add_argument("--top", type=int, default=40); ap.add_argument("--csv")
a = ap.parse_args()
con = db.connect()

lg = con.execute("SELECT r.run_id, r.retrieved_at FROM fetch_runs r WHERE source_id='espn_league' AND endpoint='players' AND ok=1 ORDER BY run_id DESC LIMIT 1").fetchone()
pub = con.execute("SELECT r.run_id, r.retrieved_at, r.season_id FROM fetch_runs r WHERE source_id='espn_public' AND endpoint='players' AND ok=1 ORDER BY run_id DESC LIMIT 1").fetchone()
run, basis, fresh = (lg["run_id"], "league scoring", lg["retrieved_at"]) if lg else (pub["run_id"], "ESPN DEFAULT scoring (league not connected yet)", pub["retrieved_at"])
season = pub["season_id"]
names = {r["stat_id"]: r["abbrev"] for r in con.execute("SELECT * FROM stat_ids")}

rows = con.execute(f"""
  SELECT p.espn_id, p.full_name, p.default_position pos, t.abbrev team, s.espn_rank, s.adp, s.injury_status,
         s.on_team_id, s.pct_owned, pr.applied_total proj_pts, pr.stats_json proj, la.applied_total last_pts
  FROM player_snapshots s JOIN players p USING (espn_id)
  LEFT JOIN pro_teams t ON t.pro_team_id = s.pro_team_id
  LEFT JOIN stat_lines pr ON pr.run_id=s.run_id AND pr.espn_id=s.espn_id AND pr.split_code='10{season}'
  LEFT JOIN stat_lines la ON la.run_id=s.run_id AND la.espn_id=s.espn_id AND la.split_code='00{season-1}'
  WHERE s.run_id=? AND s.espn_rank IS NOT NULL AND (s.on_team_id IS NULL OR s.on_team_id=0)
  {"AND p.default_position=?" if a.pos else ""}
  ORDER BY s.espn_rank LIMIT ?""", (run, a.pos, a.top) if a.pos else (run, a.top)).fetchall()

def fmt(v):
    return f"{v:.1f}" if v else "-"

def line(r):
    st = {names.get(int(k), k): v for k, v in json.loads(r["proj"] or "{}").items()}
    keys = ["W", "GAA", "SV%", "SO"] if r["pos"] == "G" else ["G", "A", "PPP", "SOG", "HIT", "BLK"]
    return " ".join(f"{k}{st[k]:.0f}" if k not in ("GAA", "SV%") else f"{k}{st[k]:.3f}" for k in keys if k in st)

print(f"Draft board | projections: {basis} | data pulled {fresh} UTC\n")
print(f"{'Rk':>3} {'Player':24} {'Pos':3} {'Team':4} {'ADP':>5} {'ProjPts':>7} {'LastPts':>7}  Status  Projection")
out = []
for r in rows:
    flag = "" if r["injury_status"] in (None, "ACTIVE") else r["injury_status"]
    print(f"{r['espn_rank']:>3} {r['full_name'][:24]:24} {r['pos']:3} {(r['team'] or '?'):4} {r['adp'] or 0:5.1f} "
          f"{fmt(r['proj_pts']):>7} {fmt(r['last_pts']):>7}  {flag:7} {line(r)}")
    out.append({k: r[k] for k in r.keys() if k != "proj"} | {"projection": line(r), "basis": basis, "pulled_utc": fresh})
if a.csv:
    with open(a.csv, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=out[0].keys()); w.writeheader(); w.writerows(out)
    print(f"\nSaved {a.csv}")
