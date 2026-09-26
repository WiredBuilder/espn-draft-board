"""Refresh RSS feeds and/or show recent news.
  .venv/bin/python scripts/news.py              # refresh feeds, list latest headlines
  .venv/bin/python scripts/news.py --player "Quinn Hughes"
"""
import argparse, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fhdb import db, rss

ap = argparse.ArgumentParser(); ap.add_argument("--player"); ap.add_argument("--no-refresh", action="store_true")
ap.add_argument("--top", type=int, default=15)
a = ap.parse_args()
con = db.connect()
if not a.no_refresh:
    for label, n in rss.refresh(con):
        print(f"{label}: {n if n == 'FAILED' else str(n) + ' new'}")
    print()
if a.player:
    rows = con.execute("""SELECT n.published_at, n.title, n.author, n.link, m.in_title, m.match_method, p.full_name
        FROM news_player_mentions m JOIN news_items n USING (guid) JOIN players p USING (espn_id)
        WHERE p.full_name LIKE ? ORDER BY n.published_at DESC LIMIT ?""", (f"%{a.player}%", a.top)).fetchall()
else:
    rows = con.execute("""SELECT published_at, title, author, link, NULL in_title, NULL match_method, NULL full_name
        FROM news_items ORDER BY published_at DESC LIMIT ?""", (a.top,)).fetchall()
for r in rows:
    tag = f" [{r['full_name']}{' in headline' if r['in_title'] else ''}]" if r["full_name"] else ""
    print(f"{(r['published_at'] or '')[:16]}  {r['title']} ({r['author']}){tag}\n    {r['link']}")
