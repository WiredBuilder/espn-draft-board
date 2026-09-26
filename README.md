# espn-draft-board

**ESPN fantasy hockey draft assistant in Python.** Pulls the ESPN fantasy API, rescores every projection under your league's rules, and prints the next pick during your draft. Runs in a terminal; works as a Claude Code or ChatGPT helper by pasting the board.

A read-only draft board for ESPN fantasy hockey. It pulls ESPN's projections and ADP, rescores every player under **your league's** scoring, ranks them by value over replacement for the roster slots you still need, and during the draft prints one line: the pick and a backup. Nothing here writes to ESPN. You click Draft.

Built and used for real on 2026-09-25 in a 13-team, 20-round, no-bench league. Write-up: https://wiredbuilder.com/lab/draft-board

## What nobody else does: it models the other owners

Every other ESPN tool ranks players. This one also reads your league's past drafts (`scripts/league_history.py`) and builds a model of each owner: how often they autopick, when they take their first goalie and first defenceman, and which players they re-draft year after year. Between your picks the board walks every intervening pick with that owner's habits instead of assuming ADP, then prints what it expects to vanish and a positional run alarm:

```
Layer 2: 4 past drafts, 1040 picks, 18% autopick. Owners modelled: 17 (goalie timing, D timing, repeat picks).
!!! G run: 3 G likely gone before pick 48, best G VOR drops 7
>>> PICK: Jake Oettinger (G, DAL) | backup: Jake Guentzel (F, TB)
    Expected before your next pick: Tkachuk (adp), Hughes (favorite), Oettinger (first G), Wedgewood (first G) ...
```

That output is a replay of pick 31 in a real draft. Five goalies went in the next twelve picks.

## How it works

1. `scripts/refresh.py` pulls the public ESPN player pool (projections, ADP, ownership, injury status) and, with your login cookies, your league's settings, scoring, rosters and draft picks. Everything lands in a local SQLite file.
2. `fhdb/rank.py` rescores projections with your league's point values, sets a replacement level per position from your league size and roster slots, and computes value over replacement (VOR) and value over next available (VONA).
3. `scripts/draft_board.py --watch 5` redraws the top of the board every 5 seconds and prints `>>> PICK: name | backup: name`.
4. During the draft, ESPN's read API usually does not show live picks. So `sync.js` reads the draft room's own Picks panel in the browser, you paste the output into `taken.txt`, and the board drops those players on the next tick. Verified on a full 260-pick mock and a real draft.
5. `scripts/news.py` pulls DobberHockey RSS headlines and tags the players named, for injury and line-change checks the night before.

## Quickstart

```bash
git clone https://github.com/WiredBuilder/espn-draft-board.git
cd espn-draft-board
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env            # set ESPN_LEAGUE_ID, ESPN_SEASON, MY_TEAM_ID
.venv/bin/python scripts/set_login.py   # private league only: pastes espn_s2 and SWID cookies into .env, hidden
.venv/bin/python scripts/refresh.py
.venv/bin/python scripts/draft_board.py --top 25
```

Draft night:

```bash
.venv/bin/python scripts/draft_board.py --watch 5 --top 25 --taken-file taken.txt --skip-file skip.txt
```

Then, after each pick, run `sync.js` in the draft room tab, paste its output over `taken.txt`, and read the `>>> PICK` line.

Where the cookies live: Chrome, logged in to ESPN, DevTools > Application > Cookies > fantasy.espn.com, values `espn_s2` and `SWID`. They stay in `.env`, which is git-ignored.

## Other commands

- `scripts/board.py --pos D --top 20` static board by position
- `scripts/news.py --player "Quinn Hughes"` news about one player
- `scripts/league_history.py` pulls your league's past drafts (needed for the owner models above); `scripts/history_report.py` writes a readable report of who takes goalies early, who autopicks, and what survives to your slot
- `scripts/mock_sim.py` simulate a draft against ADP plus autopick behaviour

## What it does not do

- It never drafts, queues, or clicks anything on ESPN.
- It has no rookie projections. ESPN projects zero for most first-year players, so they do not appear on the board. Keep your own list. Adding an NHL API rookie feed is the next planned change.
- ESPN's API is unofficial and has no published terms for automated use. This tool makes a handful of read requests per refresh.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest tests
```

## Licence

MIT.
