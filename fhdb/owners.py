"""Layer 2: what each owner in this league actually does on draft night, from draft_history.

An owner model is a dict:
  human_pct   share of their past picks they clicked themselves (rest were ESPN autopick)
  seasons     how many past drafts they appear in
  first_g     median overall pick where they took their first goalie
  first_d     median overall pick where they took their first defenceman
  favorites   player names they drafted in two or more seasons
The between-picks simulation uses this instead of assuming everyone drafts by ADP."""
from statistics import median


def _median(xs):
    return median(xs) if xs else None


def models(con):
    rows = [dict(r) for r in con.execute("SELECT * FROM draft_history ORDER BY season_id, overall_pick")]
    by_owner = {}
    for r in rows:
        by_owner.setdefault(r["owner_name"], []).append(r)
    out = {}
    for owner, picks in by_owner.items():
        seasons = sorted({p["season_id"] for p in picks})
        first_g, first_d, names = [], [], {}
        for s in seasons:
            sp = [p for p in picks if p["season_id"] == s]
            g = [p["overall_pick"] for p in sp if p["slot"] == "G"]
            d = [p["overall_pick"] for p in sp if p["slot"] == "D"]
            if g:
                first_g.append(min(g))
            if d:
                first_d.append(min(d))
            for p in sp:
                if p["player_name"]:
                    names.setdefault(p["player_name"], set()).add(s)
        out[owner] = {
            "human_pct": 100.0 * sum(1 for p in picks if not p["auto_draft"]) / len(picks),
            "seasons": len(seasons),
            "first_g": _median(first_g),
            "first_d": _median(first_d),
            "favorites": {n for n, ss in names.items() if len(ss) >= 2},
        }
    return out


def summary(con, mods):
    """One line for the top of the board, so you can see Layer 2 is loaded."""
    n = con.execute("SELECT COUNT(*), COUNT(DISTINCT season_id) FROM draft_history").fetchone()
    if not n or not n[0]:
        return "Layer 2: no draft history loaded (run scripts/league_history.py). Others modelled by ADP only."
    auto = con.execute("SELECT 100.0*SUM(auto_draft!=0)/COUNT(*) FROM draft_history").fetchone()[0] or 0
    return (f"Layer 2: {n[1]} past drafts, {n[0]} picks, {auto:.0f}% autopick. "
            f"Owners modelled: {len(mods)} (goalie timing, D timing, repeat picks).")


def simulate(avail, plan, already=None, reach=13):
    """Walk the intervening picks. `plan` is a list of (pick_no, owner_model_or_None, mode) where mode is
    "adp" or "rank". `already` maps owner name -> set of slots that owner has filled so far this draft.
    A favourite is only taken once the pick is within `reach` picks of the player's ADP (one round by
    default): owners re-draft their guys, but not 90 picks early.
    Returns (gone_ids, log) where log is a list of (pick_no, owner, player_dict, reason)."""
    already = already or {}
    left, gone, log = list(avail), set(), []
    filled = {k: set(v) for k, v in already.items()}
    for pick_no, o, mode in plan:
        if not left:
            break
        name = o.get("name") if o else None
        have = filled.setdefault(name, set())
        choice, why = None, mode
        if o:
            fav = next((x for x in left if x["full_name"] in o["favorites"] and (x["adp"] or 999) <= pick_no + reach), None)
            if fav:
                choice, why = fav, "favorite"
            elif o["first_g"] and pick_no >= o["first_g"] and "G" not in have:
                choice, why = min((x for x in left if x["slot"] == "G"), key=lambda x: x["adp"] or 999, default=None), "first G"
            elif o["first_d"] and pick_no >= o["first_d"] and "D" not in have:
                choice, why = min((x for x in left if x["slot"] == "D"), key=lambda x: x["adp"] or 999, default=None), "first D"
        if choice is None:
            key = (lambda x: x["espn_rank"] or 9999) if mode == "rank" else (lambda x: x["adp"] or 999)
            choice, why = min(left, key=key), mode
        gone.add(choice["espn_id"]); left.remove(choice); have.add(choice["slot"])
        log.append((pick_no, name, choice, why))
    return gone, log
