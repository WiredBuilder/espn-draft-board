# ESPN Fantasy Hockey Draft Assistant (free, open source)

**espn-draft-board is a free, open-source ESPN fantasy hockey draft assistant.** It rescores ESPN's projections under your league's own scoring, models how each owner in your league drafts from their past drafts, and names your next pick during a live ESPN draft. It runs in a terminal or as a Claude Code skill, and it is read-only: it never touches your ESPN team.

A read-only draft board for ESPN fantasy hockey. It pulls ESPN's projections and ADP, rescores every player under **your league's** scoring, ranks them by value over replacement for the roster slots you still need, and during the draft prints one line: the pick and a backup. Nothing here writes to ESPN. You click Draft.

Built and used for real on 2026-09-25 in a 13-team, 20-round, no-bench league. Write-up: [How I built an ESPN fantasy hockey draft board](https://wiredbuilder.com/lab/espn-fantasy-hockey-draft-assistant-free-open-source/)

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
git clone https://github.com/WiredBuilder/espn-fantasy-hockey-draft-assistant.git
cd espn-fantasy-hockey-draft-assistant
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

## It prints the rules it is using

Every run starts with the league it thinks it is drafting for, so a wrong league id or a stale cookie shows up before the draft, not during it:

```
League: 13 teams | starters F12 D6 G2 | bench 3 | IR 0
Scoring: W 2, SO 3, OTL 1, G 1, A 1, PPG 1, SHG 2, SHA 1, GWG 1, HAT 3
Ignored (rate stats cannot be summed): GAA
Replacement level (teams x depth F14 D7 G2): F 45, D 25, G 56
```

Bench seats are spread across F, D and G in proportion to starters and deepen the replacement level. C, LW, RW and UTIL slots all count as forwards. GAA and SV% are per-game rates, so they are skipped and named. If the league has no scoring or no roster slots loaded, the board refuses to run.

## Use it with Claude Code

The repo is also a Claude Code plugin with one skill, `espn-draft-board`. In Claude Code:

```
/plugin marketplace add WiredBuilder/espn-fantasy-hockey-draft-assistant
/plugin install espn-draft-board@wiredbuilder
```

No plugin marketplace? Clone it straight into your skills folder instead: `git clone https://github.com/WiredBuilder/espn-fantasy-hockey-draft-assistant.git ~/.claude/skills/espn-draft-board` (or a project's `.claude/skills/`). On Claude.ai (Pro, Max, Team, Enterprise with code execution) zip the repo folder and upload it under Settings > Features > Skills; on the API use the `/v1/skills` endpoints.

Then open Claude Code in your clone of this repo and say "set up my ESPN draft board" or, on draft night, paste the `sync.js` output and ask "who do I pick?". Claude updates `taken.txt`, runs the board, and answers with the `>>> PICK` line and any goalie or defence run alarm. You still enter your ESPN cookies yourself with `scripts/set_login.py`; the skill never asks for them in chat.

## Other commands

- `scripts/board.py --pos D --top 20` static board by position
- `scripts/news.py --player "Quinn Hughes"` news about one player
- `scripts/league_history.py` pulls your league's past drafts (needed for the owner models above); `scripts/history_report.py` writes a readable report of who takes goalies early, who autopicks, and what survives to your slot
- `scripts/mock_sim.py` simulate a draft against ADP plus autopick behaviour

## What it does not do

- It never drafts, queues, or clicks anything on ESPN.
- It has no rookie projections. ESPN projects zero for most first-year players, so they do not appear on the board. Keep your own list. Adding an NHL API rookie feed is the next planned change.
- ESPN's API is unofficial and has no published terms for automated use. This tool makes a handful of read requests per refresh.

## How it compares

| | espn-draft-board | [flaim](https://github.com/jdguggs10/flaim) | [PuckAPI skills](https://github.com/PuckAPI/claude-sports-analytics) | [espn-fantasy-claude-openclaw](https://github.com/garavitgabriel/espn-fantasy-claude-openclaw) |
|---|---|---|---|---|
| Sport | Hockey | Football, baseball, basketball, hockey | NHL analytics and betting | Baseball |
| Fantasy platform | ESPN | ESPN, Yahoo, Sleeper | None | ESPN |
| Focus | Draft day | League data over MCP | Research and models | Season management |
| Models each owner from past drafts | Yes | No | No | No |
| Runs locally, no hosted service | Yes | No (hosted app) | Uses PuckAPI server for live data | Yes |
| Claude Code skill | Yes | Yes | Yes | Yes |

## FAQ

**What is the best free draft tool for ESPN fantasy hockey?**
If your league uses custom points scoring, a board rescored for those points is more accurate than ranking by ESPN's default projections. espn-draft-board does that rescoring, adds a model of each owner's draft habits, and is free and MIT-licensed.

**Does it work with private ESPN leagues?**
Yes. Run `scripts/set_login.py` once to store your `espn_s2` and `SWID` cookies in the git-ignored `.env`. Public leagues need no login.

**Does it draft for me?**
No. It never drafts, queues, or clicks anything on ESPN. It tells you the pick; you click Draft.

**Does it support categories (H2H categories or roto) leagues?**
Not yet. The value model is points-based: projected stats times your league's point values.

**Does it support auction drafts or keeper leagues?**
It is built for snake drafts and has no bid values. Keeper picks that ESPN records in the draft are treated as taken.

**Can I use it with ChatGPT or another AI?**
Yes. The board is plain terminal text, so you can paste it into any chat. The Claude Code skill automates the loop of updating picks and re-running the board.

**Does it work for ESPN fantasy football, basketball, or baseball?**
No. It is hockey-only: positions (F, D, G), stat IDs and news feeds are NHL-specific.

## Tests

```bash
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/python -m pytest tests
```

## Licence

MIT.
