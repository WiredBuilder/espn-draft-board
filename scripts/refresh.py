"""Refresh fantasy hockey data (read-only).
Usage:  .venv/bin/python scripts/refresh.py            # public + league (league skipped if no login)
        .venv/bin/python scripts/refresh.py --public   # public player pool only
"""
import argparse, os, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fhdb import db, espn

ap = argparse.ArgumentParser()
ap.add_argument("--public", action="store_true")
ap.add_argument("--season", type=int)
args = ap.parse_args()
espn.load_env()
season = args.season or int(os.environ.get("ESPN_SEASON", 2027))
league = int(os.environ["ESPN_LEAGUE_ID"])
con = db.connect()

n, t = espn.refresh_public(con, season)
print(f"Public ESPN player pool: {n} players, {t} NHL teams (season {season}).")
if args.public:
    sys.exit(0)
if not espn.cookies():
    print("League skipped: ESPN_S2 / ESPN_SWID not set in .env (league is private).")
    sys.exit(0)
try:
    run, np = espn.refresh_league(con, league, season, os.environ.get("MY_TEAM_NAME"), int(os.environ["MY_TEAM_ID"]))
except Exception as e:
    print(f"League refresh FAILED ({type(e).__name__}). Check that the cookies in .env are current.")
    sys.exit(1)
L = con.execute("SELECT * FROM league_snapshots WHERE run_id=?", (run,)).fetchone()
print(f"League: {L['league_name']} | {L['team_count']} teams | scoring {L['scoring_type']} | "
      f"draft {L['draft_type']} at {L['draft_date']} | drafted={bool(L['drafted'])}")
print(f"League-scored player pool: {np} players.")
