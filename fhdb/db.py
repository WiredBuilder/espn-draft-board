"""SQLite helpers. Database lives in ./data (outside any skill package)."""
import datetime as _dt
import os
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = Path(os.environ.get("FH_DB_PATH", ROOT / "data" / "fantasy_hockey.sqlite"))
SCHEMA_VERSION = "1"

SOURCES = [
    ("espn_public", "ESPN Fantasy public player pool", "https://lm-api-reads.fantasy.espn.com/apis/v3/games/fhl", "fact+projection", 0,
     "ESPN default scoring projections, ADP, ownership, ESPN injury designation. Unofficial API, no published terms for automated use."),
    ("espn_league", "ESPN Fantasy league (yours)", "https://fantasy.espn.com/hockey/", "fact", 1,
     "Private league: needs ESPN_S2 + ESPN_SWID cookies. Read-only."),
    ("espn_league_history", "ESPN Fantasy league (yours), past seasons", "https://fantasy.espn.com/hockey/", "fact", 1,
     "Completed drafts from prior seasons: who took whom, when, and whether it was an autopick. Read-only."),
    ("dobberhockey", "DobberHockey (RSS)", "https://dobberhockey.com", "opinion", 0,
     "Public RSS feeds, updated hourly. Analyst opinion, not fact. Store headline, link, author, short excerpt only."),
]

# Stat labels. verified=1 where ESPN's own UI/scoring settings confirm it; others are best guesses.
STAT_IDS = {
    0: ("GS", 0), 1: ("W", 1), 2: ("L", 1), 3: ("SA", 0), 4: ("GA", 1), 6: ("SV", 1), 7: ("SO", 1),
    9: ("OTL", 0), 10: ("GAA", 1), 11: ("SV%", 1), 13: ("G", 1), 14: ("A", 1), 15: ("+/-", 1),
    17: ("PIM", 1), 18: ("PPG", 1), 19: ("PPA", 1), 20: ("SHG", 1), 21: ("SHA", 1), 22: ("GWG", 1),
    23: ("FOW", 1), 24: ("FOL", 1), 26: ("TTOI", 0), 27: ("ATOI", 0), 28: ("HAT", 0), 29: ("SOG", 1),
    31: ("HIT", 1), 32: ("BLK", 1), 33: ("DEF", 0), 34: ("GP", 1), 35: ("STPG", 0), 36: ("STPA", 0),
    37: ("STP", 0), 38: ("PPP", 1), 39: ("SHP", 1),
}


def now_utc() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


def connect(path=None) -> sqlite3.Connection:
    p = Path(path or DEFAULT_DB)
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    # TRUNCATE keeps the journal file instead of deleting it (works on synced/mounted folders
    # that forbid file deletion) while staying crash-safe.
    con.execute("PRAGMA journal_mode=TRUNCATE")
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init(con)
    return con


def init(con: sqlite3.Connection) -> None:
    con.executescript((Path(__file__).parent / "schema.sql").read_text())
    con.execute("INSERT OR REPLACE INTO schema_meta VALUES ('schema_version', ?)", (SCHEMA_VERSION,))
    con.executemany("INSERT OR REPLACE INTO sources VALUES (?,?,?,?,?,?)", SOURCES)
    con.executemany("INSERT OR IGNORE INTO stat_ids VALUES (?,?,?)",
                    [(k, v[0], v[1]) for k, v in STAT_IDS.items()])
    con.commit()


def start_run(con, source_id, endpoint, season_id, note=None) -> int:
    cur = con.execute(
        "INSERT INTO fetch_runs (source_id, endpoint, season_id, retrieved_at, ok, note) VALUES (?,?,?,?,0,?)",
        (source_id, endpoint, season_id, now_utc(), note))
    return cur.lastrowid


def finish_run(con, run_id, ok, http_status=None, row_count=None, note=None):
    con.execute("UPDATE fetch_runs SET ok=?, http_status=?, row_count=?, note=COALESCE(?, note) WHERE run_id=?",
                (1 if ok else 0, http_status, row_count, note, run_id))
    con.commit()
