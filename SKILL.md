---
name: espn-draft-board
description: Run a live draft board for an ESPN fantasy hockey league, rescored to that league's own scoring, with owner-by-owner modelling of the other drafters from past drafts. Use this whenever the user mentions an ESPN fantasy hockey draft, draft board, draft night, mock draft, "who should I pick", league scoring, value over replacement, or wants help preparing for or sitting through a fantasy hockey draft, even if they do not say "draft board". Also use it when the user says "sync" during a draft.
compatibility: Python 3.10+, a terminal, and for private leagues the user's own ESPN cookies (espn_s2, SWID). Read-only against ESPN; it never drafts, queues or clicks.
---

# ESPN fantasy hockey draft board

This repo is the skill. The scripts do the work; your job is to run them in the right order, keep the taken list current during the draft, and answer in two lines. Everything is read-only against ESPN. The user clicks Draft.

## Why it exists

ESPN's draft room ranks players under ESPN's default scoring (hits, blocks, shots). Most leagues score differently, so that list is quietly wrong all night. This board re-prices ESPN's projections under the league's real scoring, sets a replacement level from the league's roster shape, and models each other owner from the league's past drafts (when they take goalies, who they re-draft, whether they autopick). Then it prints one line: the pick and a backup.

## Setup (once, before draft night)

Run from the repo root. Use the repo's own venv so the user's Python stays clean.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
```

Edit `.env`: `ESPN_LEAGUE_ID` (from the league URL), `ESPN_SEASON` (the season end year, 2027 for 2026-27), `MY_TEAM_ID` (from the team URL `teamId=`). `MY_TEAM_NAME` is optional.

Private league (ESPN returns 401 without login): the user runs `.venv/bin/python scripts/set_login.py` themselves and pastes the two cookies into a hidden prompt. Never ask the user to paste cookies into chat, and never read `.env` back to them. Where the cookies live: Chrome, logged in to ESPN, DevTools > Application > Cookies > fantasy.espn.com, `espn_s2` and `SWID`.

Then:

```bash
.venv/bin/python scripts/refresh.py          # player pool + league settings, scoring, rosters
.venv/bin/python scripts/league_history.py   # past drafts, feeds the owner models (Layer 2)
.venv/bin/python scripts/draft_board.py --top 25
```

No cookies yet? `scripts/board.py --top 25` shows a preview under ESPN's default scoring from the public pool alone, so the user has something to look at. Say clearly that it is not their league's scoring. `draft_board.py` refuses to run until the league has been pulled.

The board prints the rules it is running on first. Read that block back to the user and confirm it matches their league (teams, starters, bench, scoring). If it says "League settings incomplete", the league id or cookies are wrong; fix that before anything else. If the Layer 2 line says "no draft history loaded", `league_history.py` has not run or the league is new; the board falls back to ADP and says so.

## Before the draft

Useful checks the night before:

- `.venv/bin/python scripts/board.py --pos D --top 20` for one position (`F`, `D`, `G`), and `.venv/bin/python scripts/mock_sim.py --slot 4 --teams 13 --upto 100` to see what usually survives to a slot.

- `.venv/bin/python scripts/history_report.py` writes a report of who takes goalies early, who autopicks, and what usually survives to the user's slot. Summarise the three things that change the plan (goalie timing, D cliff, the owners picking right before them).
- `.venv/bin/python scripts/news.py --player "Name"` for injury headlines on anyone the user is targeting.
- Write `skip.txt`, one name per line, for players the user never wants recommended (long-term injuries with no bench slot, personal rules). Pass it with `--skip-file skip.txt`.

Rookies: ESPN projects zero for most first-year players, so they never appear on the board. If the user drafts rookies, keep a short hand list with them and say plainly that the board cannot rank those.

## Draft night

Start the board in a terminal the user can see and leave it running:

```bash
.venv/bin/python scripts/draft_board.py --watch 5 --top 25 --taken-file taken.txt --skip-file skip.txt
```

ESPN's read API usually does not publish picks while the draft is live, so the taken list comes from the draft room page itself. `sync.js` reads the room's Picks panel (Activity panel set to "Picks") and returns one name per line, with `* ` in front of the user's own picks. Run it with whatever browser tool is available (a console paste, or a browser automation tool's JavaScript runner on the draft room tab), or take the output the user pastes to you, write it to `taken.txt`, and the board updates within 5 seconds. Read the board's `>>> PICK` line back.

Rules that keep this safe and fast:

- Never click, draft, queue or type anything in the draft room. Reading the page is the only interaction.
- When the user says "sync", do exactly that: run the snippet, rewrite `taken.txt`, read the board, reply. No commentary.
- Reply in two lines during the draft: the `>>> PICK` line with its backup, then one line of state (picks made, picks until theirs, any `!!!` run alarm). Two minutes per pick is not long.
- The Picks panel can reset when the page reloads and show only recent picks. The snippet returns round and pick numbers, so append the new names rather than overwriting, and check the count against the room's "on the clock" pick number.
- Watch for name collisions in the room's search (Laferriere vs Lafreniere). Always include the team in the pick line so the user clicks the right one.
- If the board's top pick is someone on the user's skip list or flagged OUT, the skip file is missing; say the next healthy name instead.

## Reading the board

- `Pts` is the projection under the league's scoring. `VOR` is points above the replacement player at that slot. `VONA` is what the user loses at that slot by waiting until their next pick, given the owner models between now and then. The board sorts by VONA.
- `Waiting costs` and `Expected before your next pick` come from walking each intervening owner with their habits. `!!! G run` means two or more goalies are expected to go before the user's next pick and the best goalie value drops by 5 or more. That is the cue to take a goalie now.
- When the user disagrees with the board, give the one number that settles it (the VONA gap or the projection gap) and let them decide. The plan they wrote before the draft beats the board on timing questions; the board beats the plan on who is actually left.

## After the draft

Offer a recap: their roster with projections, where the board and ESPN disagreed, what the board missed. Log anything the board got wrong as a note for next season.
