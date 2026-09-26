---
name: espn-draft-board
description: "ESPN fantasy hockey draft assistant. Builds a league-specific draft board from the ESPN fantasy API, models each owner from past drafts, and names the next pick during a live draft. Use when the user mentions an ESPN fantasy hockey draft, draft board, draft prep, mock draft, who to pick next, goalie or defence runs, sleepers, or pastes picks from the ESPN draft room."
---

# ESPN Fantasy Hockey Draft Board

Read-only. Nothing here drafts, queues, or clicks on ESPN. The user always clicks Draft.

All commands run from the root of the `espn-draft-board` repo with its virtualenv: `.venv/bin/python ...`. If there is no `.venv` or `.env`, do Setup first.

## Setup (once per season)

1. `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`
2. `cp .env.example .env`, then ask the user for `ESPN_LEAGUE_ID`, `ESPN_SEASON`, `MY_TEAM_ID` and write them to `.env`. The league ID is the `leagueId=` value in their ESPN league URL.
3. Private league only: tell the user to run `.venv/bin/python scripts/set_login.py` themselves. It reads the `espn_s2` and `SWID` cookies with hidden input. **Never ask the user to paste cookies into chat, and never read or print them from `.env`.**
4. `.venv/bin/python scripts/refresh.py` pulls the player pool and league settings into local SQLite.
5. `.venv/bin/python scripts/league_history.py` then `.venv/bin/python scripts/history_report.py` pull past drafts. This powers the owner models. Skip only if the league has no history.

## Draft prep

- Overall board: `.venv/bin/python scripts/draft_board.py --top 40`
- By position: `.venv/bin/python scripts/board.py --pos D --top 20` (`F`, `D`, or `G`)
- Mock from a draft slot: `.venv/bin/python scripts/mock_sim.py --slot 4 --teams 13 --upto 100`
- News check the night before: `.venv/bin/python scripts/news.py`, or `--player "Name"` for one player

Summarize in plain terms: who the board likes at the user's slot, when the owner models expect the first goalie and defence runs, and which players the board ranks well above ESPN ADP.

## Live draft loop

ESPN's read API usually does not show live picks, so the draft room is the source of truth.

1. The user runs `sync.js` in the ESPN draft room tab (browser console) and pastes its output to you.
2. Overwrite `taken.txt` with that output, one name per line.
3. Run `.venv/bin/python scripts/draft_board.py --top 10 --taken-file taken.txt --skip-file skip.txt`
4. Reply with the `>>> PICK:` line first, then any `!!!` run alarm, then one line on why. Keep it short; the user is on the clock.

If the user would rather watch a terminal, give them: `.venv/bin/python scripts/draft_board.py --watch 5 --top 25 --taken-file taken.txt --skip-file skip.txt`

## Known limits (say these when relevant)

- No rookie projections: ESPN projects zero for most first-year players, so they are missing from the board. Ask the user for their rookie list and add it to their own judgement.
- ESPN's API is unofficial. A refresh makes a handful of read requests; do not loop `refresh.py`.
