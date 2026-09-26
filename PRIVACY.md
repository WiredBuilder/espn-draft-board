# Privacy

This plugin runs on your machine. It has no server, no account, no telemetry, and it sends nothing to Wired Builder.

## What it reads

- **ESPN's public player pool** (projections, ADP, ownership, injury status) from `lm-api-reads.fantasy.espn.com`. No login is needed.
- **Your own ESPN league** (settings, teams, rosters, draft history) from the same ESPN API. Private leagues need your ESPN login cookies, `espn_s2` and `SWID`. You paste them yourself with `scripts/set_login.py`, which stores them in a git-ignored `.env` file on your machine. The plugin never reads your browser's cookie store, keychain, or any other credential store.
- **DobberHockey RSS feeds** from `dobberhockey.com`, for injury and lineup news. No login.

## Where the data goes

- Your cookies are sent only to ESPN, only to fetch your league. They are never printed, logged, or sent anywhere else.
- Everything fetched is stored in a local SQLite file, `data/fantasy_hockey.sqlite`, on your machine. That includes team names and owner display names from your league, which ESPN exposes to every member of the league.
- Nothing is retained by the author. There is no service on the author's side to retain it.

## What it never does

- It never writes to ESPN. It does not draft, queue, trade, or change your team.
- It never reads Claude's conversation history, memory, or files outside this repository and its `.env` and `data/` folders.

## Deleting your data

Delete `.env` and `data/fantasy_hockey.sqlite`. That is all of it.

Questions: open an issue at https://github.com/WiredBuilder/espn-fantasy-hockey-draft-assistant/issues.
