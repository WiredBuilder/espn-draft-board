"""Layer 2: what THIS league's owners actually do on draft night (from draft_history).
  .venv/bin/python scripts/history_report.py            # prints and writes docs/league-history-report.md
"""
import sys, statistics as st
from collections import defaultdict
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fhdb import db
con = db.connect()
H = [dict(r) for r in con.execute("SELECT * FROM draft_history ORDER BY season_id, overall_pick")]
seasons = sorted({h["season_id"] for h in H})
lg = con.execute("SELECT MAX(run_id) FROM fetch_runs WHERE source_id='espn_league' AND endpoint='league' AND ok=1").fetchone()[0]
cur = [dict(r) for r in con.execute("SELECT team_id, name, owner_names, draft_position, is_mine FROM fantasy_teams WHERE run_id=? ORDER BY draft_position", (lg,))]
T = len(cur)
out = []
P = lambda s="": out.append(s)

P("# League draft history report"); P()
P(f"Seasons: {', '.join(str(s-1)+'-'+str(s)[2:] for s in seasons)} draft nights. {len(H)} picks. Written from `draft_history`.")
P("ESPN's per-season 'rank' looks like a season-end rank, not preseason, so this report uses timing and outcomes, not reach-vs-rank."); P()

P("## 1. League-wide, per season"); P()
P("| Season | Teams | Autopicks | G taken by pick 60 | D taken in rounds 1-4 | First G at pick | 2 G by pick |")
P("|---|---|---|---|---|---|---|")
for s in seasons:
    hs = [h for h in H if h["season_id"] == s]; n = max(h["team_id"] for h in hs) and len({h["team_id"] for h in hs})
    auto = sum(1 for h in hs if h["auto_draft"]); g60 = sum(1 for h in hs if h["slot"] == "G" and h["overall_pick"] <= 60)
    d4 = sum(1 for h in hs if h["slot"] == "D" and h["round_id"] <= 4)
    gp = [h["overall_pick"] for h in hs if h["slot"] == "G"]
    P(f"| {s-1}-{str(s)[2:]} | {n} | {auto} ({100*auto//len(hs)}%) | {g60} | {d4} | {min(gp) if gp else '-'} | {sorted(gp)[1] if len(gp)>1 else '-'} |")
P()

# per-owner
own = defaultdict(list)
for h in H:
    if h["owner_key"]: own[h["owner_key"]].append(h)
name_of = {k: max(v, key=lambda h: h["season_id"])["owner_name"] for k, v in own.items()}
cur_owner = {c["owner_names"]: c for c in cur}
def first_pick(hs, slot):
    x = [h["overall_pick"] for h in hs if h["slot"] == slot]; return min(x) if x else None
rows = []
for k, hs in own.items():
    by_s = defaultdict(list)                      # one entry per (season, team): some owners run two teams
    for h in hs: by_s[(h["season_id"], h["team_id"])].append(h)
    human = [h for h in hs if not h["auto_draft"]]
    fg = [first_pick(v, "G") for v in by_s.values() if first_pick(v, "G")]
    fd = [first_pick(v, "D") for v in by_s.values() if first_pick(v, "D")]
    d4 = [sum(1 for h in v if h["slot"] == "D" and h["round_id"] <= 4) for v in by_s.values()]
    g8 = [sum(1 for h in v if h["slot"] == "G" and h["round_id"] <= 8) for v in by_s.values()]
    # draft quality: total actual points of their picks vs the season's mean per team
    q = []
    for (s, tid), v in by_s.items():
        mine = sum((h["season_pts"] or 0) for h in v)
        teams_tot = defaultdict(float)
        for h in H:
            if h["season_id"] == s: teams_tot[h["team_id"]] += (h["season_pts"] or 0)
        rank = 1 + sum(1 for t in teams_tot.values() if t > mine)
        q.append((s, rank, len(teams_tot)))
    c = cur_owner.get(name_of[k])
    rows.append(dict(name=name_of[k], seasons=len(by_s), human_pct=round(100*len(human)/len(hs)), first_g=round(st.mean(fg)) if fg else None,
                     g_by_r8=round(st.mean(g8),1), first_d=round(st.mean(fd)) if fd else None, d_r1_4=round(st.mean(d4),1),
                     finishes=", ".join(f"{s-1}-{str(s)[2:]}: {r}/{n}" for s, r, n in sorted(q)),
                     slot27=c["draft_position"] if c else None, mine=bool(c and c["is_mine"])))
P("## 2. Owners in this year's league, what they do"); P()
P("Human % = share of their picks they clicked themselves (rest were ESPN autopick). Draft finish = rank of their drafted roster's actual points that season.")
P()
P("| 2027 slot | Owner | Team-seasons | Human % | First G at pick | G by round 8 | First D at pick | D in rounds 1-4 | Draft finish by season |")
P("|---|---|---|---|---|---|---|---|---|")
for r in sorted(rows, key=lambda r: (r["slot27"] is None, r["slot27"] or 99)):
    if r["slot27"] is None: continue
    P(f"| {r['slot27']}{' (us)' if r['mine'] else ''} | {r['name']} | {r['seasons']} | {r['human_pct']} | {r['first_g'] or '-'} | {r['g_by_r8']} | {r['first_d'] or '-'} | {r['d_r1_4']} | {r['finishes']} |")
new = [c for c in cur if c["owner_names"] not in name_of.values()]
if new: P(); P("No history (new to the league): " + ", ".join(f"slot {c['draft_position']} {c['name']} ({c['owner_names']})" for c in new))
P()

# who picks between our picks
me = next(c for c in cur if c["is_mine"]); pos = me["draft_position"]
picks = [(r - 1) * T + (pos if r % 2 else T - pos + 1) for r in range(1, 21)]
def owner_at(p):
    r = (p - 1) // T + 1; i = (p - 1) % T + 1; slot = i if r % 2 else T - i + 1
    return next((c for c in cur if c["draft_position"] == slot), None)
P("## 3. Who picks between our picks tonight (slot %d)" % pos); P()
byname = {r["name"]: r for r in rows}
for a_, b_ in [(picks[0], picks[1]), (picks[1], picks[2]), (picks[2], picks[3])]:
    P(f"**Between our {a_} and {b_}:**")
    for p in range(a_ + 1, b_):
        c = owner_at(p); r = byname.get(c["owner_names"]) if c else None
        tag = (f"first G at {r['first_g']}, first D at {r['first_d']}, {r['human_pct']}% human" if r else "no history")
        P(f"- pick {p}: {c['name'] if c else '?'} ({tag})")
    P()

P("## 4. Positional runs, all seasons"); P()
P("Average number of each slot taken per round band, per season (13-team equivalent):"); P()
P("| Rounds | F | D | G |"); P("|---|---|---|---|")
for lo, hi in [(1,2),(3,5),(6,8),(9,12),(13,20)]:
    cnt = defaultdict(float)
    for h in H:
        if lo <= h["round_id"] <= hi: cnt[h["slot"]] += 1
    P(f"| {lo}-{hi} | {cnt['F']/len(seasons):.0f} | {cnt['D']/len(seasons):.0f} | {cnt['G']/len(seasons):.0f} |")
P()

P("## 5. Outcomes: were early goalies and early D worth it?"); P()
for slot in ("F", "D", "G"):
    for lo, hi in [(1,3),(4,6),(7,10),(11,20)]:
        v = [h["season_pts"] or 0 for h in H if h["slot"] == slot and lo <= h["round_id"] <= hi]
        if len(v) >= 5: P(f"- {slot} taken in rounds {lo}-{hi}: {len(v)} picks, median {st.median(v):.0f} pts, mean {st.mean(v):.0f}")
P()
P("## 6. Loyalty: same owner drafted the same player in 2+ seasons"); P()
loy = defaultdict(set)
for h in H:
    if h["owner_key"]: loy[(h["owner_key"], h["player_name"])].add(h["season_id"])
loy = sorted(((name_of[k], p, sorted(s)) for (k, p), s in loy.items() if len(s) >= 2), key=lambda x: (-len(x[2]), x[0]))
for n, p, s in loy[:40]:
    if n in {c["owner_names"] for c in cur}: P(f"- {n}: {p} ({', '.join(str(x-1)+'-'+str(x)[2:] for x in s)})")
txt = "\n".join(out); Path("docs/league-history-report.md").write_text(txt + "\n"); print(txt)
