-- Fantasy hockey research database. Schema version 1.
-- Rule: current-state tables are upserted; *_snapshots and *_history tables keep history.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_meta (key TEXT PRIMARY KEY, value TEXT);

-- Where every piece of data came from.
CREATE TABLE IF NOT EXISTS sources (
  source_id   TEXT PRIMARY KEY,          -- e.g. 'espn_public', 'espn_league'
  name        TEXT NOT NULL,
  base_url    TEXT,
  kind        TEXT,                      -- fact | projection | opinion
  requires_auth INTEGER DEFAULT 0,
  notes       TEXT
);

-- One row per refresh call. Every snapshot row points back here (provenance + freshness).
CREATE TABLE IF NOT EXISTS fetch_runs (
  run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id    TEXT NOT NULL REFERENCES sources(source_id),
  endpoint     TEXT NOT NULL,
  season_id    INTEGER,
  retrieved_at TEXT NOT NULL,            -- UTC ISO-8601
  http_status  INTEGER,
  ok           INTEGER NOT NULL,
  row_count    INTEGER,
  note         TEXT
);

CREATE TABLE IF NOT EXISTS pro_teams (
  pro_team_id INTEGER PRIMARY KEY,
  abbrev TEXT, location TEXT, name TEXT,
  bye_or_games_json TEXT,
  updated_run_id INTEGER REFERENCES fetch_runs(run_id)
);

-- Stable identity: ESPN player id. Never match on name alone.
CREATE TABLE IF NOT EXISTS players (
  espn_id INTEGER PRIMARY KEY,
  full_name TEXT NOT NULL, first_name TEXT, last_name TEXT,
  default_position TEXT,                 -- C / LW / RW / D / G
  eligible_slots_json TEXT,
  pro_team_id INTEGER,
  jersey TEXT,
  active INTEGER,
  nhl_id INTEGER,                        -- cross-source id, filled later
  first_seen_run_id INTEGER, updated_run_id INTEGER
);

-- Point-in-time view of each player per refresh (ranks, ADP, ownership, status).
CREATE TABLE IF NOT EXISTS player_snapshots (
  run_id INTEGER NOT NULL REFERENCES fetch_runs(run_id),
  espn_id INTEGER NOT NULL REFERENCES players(espn_id),
  pro_team_id INTEGER,
  injury_status TEXT, injured INTEGER,
  espn_rank INTEGER, espn_auction_value REAL,
  adp REAL, adp_change REAL, auction_avg REAL,
  pct_owned REAL, pct_started REAL,
  on_team_id INTEGER,                    -- 0 = free agent (league refresh only)
  roster_status TEXT,                    -- FREEAGENT / WAIVERS / ONTEAM
  last_news_at TEXT,
  season_outlook TEXT,                   -- ESPN blurb, short, attributed to ESPN
  PRIMARY KEY (run_id, espn_id)
);

-- Only written when a player's status changes, so history stays readable.
CREATE TABLE IF NOT EXISTS injury_history (
  espn_id INTEGER NOT NULL REFERENCES players(espn_id),
  source_id TEXT NOT NULL,
  status TEXT NOT NULL,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  run_id INTEGER REFERENCES fetch_runs(run_id),
  PRIMARY KEY (espn_id, source_id, first_seen_at)
);

-- Stat lines: actuals, recent splits, projections. split_code = ESPN id like '102027' (projection 2027).
CREATE TABLE IF NOT EXISTS stat_lines (
  run_id INTEGER NOT NULL REFERENCES fetch_runs(run_id),
  espn_id INTEGER NOT NULL REFERENCES players(espn_id),
  split_code TEXT NOT NULL,
  season_id INTEGER,
  split_label TEXT,                      -- actual_season / last_7 / last_15 / last_30 / projection
  stat_source_id INTEGER,                -- 0 actual, 1 projection
  scoring_basis TEXT NOT NULL,           -- 'espn_default' or 'league' — never mix
  applied_total REAL, applied_average REAL,
  stats_json TEXT NOT NULL,              -- raw {statId: value}
  PRIMARY KEY (run_id, espn_id, split_code, scoring_basis)
);

-- Human names for ESPN stat ids. verified=0 means the label is a best guess.
CREATE TABLE IF NOT EXISTS stat_ids (
  stat_id INTEGER PRIMARY KEY, abbrev TEXT, verified INTEGER DEFAULT 0
);

-- League (needs auth for private leagues)
CREATE TABLE IF NOT EXISTS league_snapshots (
  run_id INTEGER PRIMARY KEY REFERENCES fetch_runs(run_id),
  league_id INTEGER, season_id INTEGER, league_name TEXT,
  team_count INTEGER, scoring_type TEXT, draft_type TEXT, draft_date TEXT,
  drafted INTEGER, settings_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS league_scoring (
  run_id INTEGER NOT NULL REFERENCES fetch_runs(run_id),
  stat_id INTEGER NOT NULL, points REAL, is_reverse INTEGER,
  PRIMARY KEY (run_id, stat_id)
);
CREATE TABLE IF NOT EXISTS league_roster_slots (
  run_id INTEGER NOT NULL REFERENCES fetch_runs(run_id),
  slot_id INTEGER NOT NULL, slot_name TEXT, count INTEGER,
  PRIMARY KEY (run_id, slot_id)
);
CREATE TABLE IF NOT EXISTS fantasy_teams (
  run_id INTEGER NOT NULL REFERENCES fetch_runs(run_id),
  team_id INTEGER NOT NULL, abbrev TEXT, name TEXT, owner_names TEXT,
  draft_position INTEGER, is_mine INTEGER DEFAULT 0,
  PRIMARY KEY (run_id, team_id)
);
CREATE TABLE IF NOT EXISTS roster_entries (
  run_id INTEGER NOT NULL REFERENCES fetch_runs(run_id),
  team_id INTEGER NOT NULL, espn_id INTEGER NOT NULL,
  lineup_slot_id INTEGER, acquisition_type TEXT,
  PRIMARY KEY (run_id, team_id, espn_id)
);
CREATE TABLE IF NOT EXISTS draft_picks (
  run_id INTEGER NOT NULL REFERENCES fetch_runs(run_id),
  overall_pick INTEGER NOT NULL, round_id INTEGER, round_pick INTEGER,
  team_id INTEGER, espn_id INTEGER, keeper INTEGER,
  PRIMARY KEY (run_id, overall_pick)
);

-- Expert rankings / opinions (imported later). Never treated as ground truth.
CREATE TABLE IF NOT EXISTS expert_rankings (
  source_id TEXT NOT NULL REFERENCES sources(source_id),
  published_date TEXT NOT NULL,
  espn_id INTEGER, raw_name TEXT NOT NULL, raw_team TEXT, raw_pos TEXT,
  overall_rank INTEGER, pos_rank INTEGER, note TEXT, url TEXT,
  match_confidence TEXT,                 -- id / name+team / unmatched
  imported_at TEXT NOT NULL,
  PRIMARY KEY (source_id, published_date, raw_name, raw_team)
);

CREATE TABLE IF NOT EXISTS strategy_prefs (
  key TEXT PRIMARY KEY, value TEXT, updated_at TEXT
);

-- Convenience views: latest snapshot per source.
CREATE VIEW IF NOT EXISTS latest_public_run AS
  SELECT MAX(run_id) AS run_id FROM fetch_runs WHERE source_id='espn_public' AND endpoint='players' AND ok=1;
CREATE VIEW IF NOT EXISTS latest_league_run AS
  SELECT MAX(run_id) AS run_id FROM fetch_runs WHERE source_id='espn_league' AND endpoint='league' AND ok=1;

-- News / analysis feeds (RSS). Headlines, links, short excerpts only; full article text is never stored.
CREATE TABLE IF NOT EXISTS feeds (
  feed_url TEXT PRIMARY KEY, source_id TEXT NOT NULL REFERENCES sources(source_id), label TEXT,
  last_fetched_at TEXT, last_http_status INTEGER, last_build_date TEXT, active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS news_items (
  guid TEXT PRIMARY KEY, source_id TEXT NOT NULL, title TEXT, link TEXT, author TEXT,
  published_at TEXT, categories TEXT, excerpt TEXT,
  first_seen_at TEXT NOT NULL, feeds_seen_in TEXT
);
-- Which players an item mentions. Matching is by full name, so match_method says how sure it is.
CREATE TABLE IF NOT EXISTS news_player_mentions (
  guid TEXT NOT NULL REFERENCES news_items(guid), espn_id INTEGER NOT NULL REFERENCES players(espn_id),
  in_title INTEGER, match_method TEXT,   -- 'full_name_unique' | 'full_name_ambiguous'
  PRIMARY KEY (guid, espn_id)
);

-- Completed drafts from past seasons (layer 2: model the league's own owners, not ESPN's crowd).
-- owner_key is a short hash of the ESPN member id so owners can be followed across seasons without storing the id.
CREATE TABLE IF NOT EXISTS draft_history (
  season_id INTEGER NOT NULL, overall_pick INTEGER NOT NULL,
  run_id INTEGER REFERENCES fetch_runs(run_id),
  round_id INTEGER, round_pick INTEGER, team_id INTEGER, team_name TEXT,
  owner_key TEXT, owner_name TEXT,
  player_id INTEGER, player_name TEXT, pos TEXT, slot TEXT,
  auto_draft INTEGER,                    -- ESPN autoDraftTypeId (0 = a human clicked)
  espn_rank INTEGER,                     -- ESPN STANDARD draft rank for that season, if returned
  adp REAL,                              -- ESPN ADP for that season, if returned
  season_pts REAL, season_gp REAL,       -- what the player actually scored that season under league rules
  PRIMARY KEY (season_id, overall_pick)
);
