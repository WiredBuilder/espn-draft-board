"""Factual one-player summaries. Every line says where it came from. No opinions except labelled Dobber headlines."""
import json

LAB = {"13": "G", "14": "A", "18": "PPG", "20": "SHG", "22": "GWG", "28": "HAT", "34": "GP",
       "1": "W", "7": "SO", "9": "OTL", "10": "GAA", "11": "SV%"}


def _line(st, goalie):
    keys = ["34", "1", "7", "9", "10", "11"] if goalie else ["34", "13", "14", "18", "20", "22"]
    out = []
    for k in keys:
        if k in st:
            v = float(st[k])
            out.append(f"{LAB[k]} {v:.3f}" if k in ("10", "11") else f"{LAB[k]} {v:.0f}")
    return ", ".join(out)


def card(con, espn_id, x=None):
    run = con.execute("SELECT MAX(run_id) FROM fetch_runs WHERE source_id='espn_league' AND endpoint='players' AND ok=1").fetchone()[0]
    p = con.execute("""SELECT p.full_name, p.default_position pos, t.location||' '||t.name team, s.injury_status, s.adp,
        s.espn_rank, s.pct_owned, s.last_news_at, r.retrieved_at FROM players p
        JOIN player_snapshots s ON s.espn_id=p.espn_id AND s.run_id=?
        JOIN fetch_runs r ON r.run_id=s.run_id
        LEFT JOIN pro_teams t ON t.pro_team_id=s.pro_team_id WHERE p.espn_id=?""", (run, espn_id)).fetchone()
    if not p:
        return "No data."
    g = p["pos"] == "G"
    lines = [f"{p['full_name']} | {p['pos']} | {p['team']}"]
    for code, label in (("002026", "2025-26 actual"), ("102027", "2026-27 ESPN projection")):
        r = con.execute("SELECT stats_json FROM stat_lines WHERE run_id=? AND espn_id=? AND split_code=?", (run, espn_id, code)).fetchone()
        lines.append(f"  {label}: {_line(json.loads(r[0]), g) if r else 'none on file'}")
    if x:
        lines.append(f"  Your league: {x['pts']:.0f} projected pts ({x['basis']}), {x['vor']:.0f} above a replacement {x['slot']}")
    inj = p["injury_status"] or "unknown"
    lines.append(f"  ESPN status: {inj}" + ("" if inj == "ACTIVE" else " (ESPN designation, not an official NHL report)")
                 + f" | ESPN rank {p['espn_rank']}, ADP {p['adp'] or 0:.1f}")
    news = con.execute("""SELECT n.title, n.published_at FROM news_player_mentions m JOIN news_items n USING(guid)
        WHERE m.espn_id=? AND m.in_title=1 ORDER BY n.published_at DESC LIMIT 1""", (espn_id,)).fetchone()
    if news:
        lines.append(f"  Dobber (opinion) {news['published_at'][:10]}: {news['title'][:110]}")
    lines.append(f"  Source: ESPN, pulled {p['retrieved_at'][:16]} UTC")
    return "\n".join(lines)
