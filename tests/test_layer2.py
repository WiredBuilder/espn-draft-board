"""Layer 2: owner models built from draft history, and the between-picks simulation that uses them."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from fhdb import db, owners, rank


def _con(tmp_path):
    con = db.connect(tmp_path / "t.sqlite")
    rows = [
        # season, pick, owner, player, slot, auto
        (2025, 20, "Ann", "Andrei Vasilevskiy", "G", 0), (2025, 33, "Ann", "Evan Bouchard", "D", 0),
        (2026, 22, "Ann", "Igor Shesterkin", "G", 0), (2026, 31, "Ann", "Evan Bouchard", "D", 0),
        (2025, 5, "Bob", "Cale Makar", "D", 1), (2025, 60, "Bob", "Juuse Saros", "G", 1),
        (2026, 8, "Bob", "Cale Makar", "D", 1), (2026, 70, "Bob", "Jake Oettinger", "G", 0),
    ]
    con.executemany("INSERT INTO draft_history (season_id, overall_pick, owner_name, player_name, slot, auto_draft, team_id, round_id, round_pick) VALUES (?,?,?,?,?,?,1,1,1)", rows)
    con.commit()
    return con


def test_models_read_timing_favorites_and_autopick(tmp_path):
    m = owners.models(_con(tmp_path))
    assert m["Ann"]["first_g"] == 21 and m["Ann"]["first_d"] == 32
    assert m["Ann"]["favorites"] == {"Evan Bouchard"}
    assert m["Ann"]["human_pct"] == 100
    assert m["Bob"]["human_pct"] == 25 and m["Bob"]["favorites"] == {"Cale Makar"}


def _pool():
    return [
        {"espn_id": 1, "full_name": "Evan Bouchard", "slot": "D", "adp": 16, "espn_rank": 16, "vor": 60},
        {"espn_id": 2, "full_name": "Nick Suzuki", "slot": "F", "adp": 20, "espn_rank": 23, "vor": 55},
        {"espn_id": 3, "full_name": "Andrei Vasilevskiy", "slot": "G", "adp": 21, "espn_rank": 22, "vor": 35},
        {"espn_id": 4, "full_name": "Jake Oettinger", "slot": "G", "adp": 45, "espn_rank": 40, "vor": 30},
        {"espn_id": 5, "full_name": "Wyatt Johnston", "slot": "F", "adp": 27, "espn_rank": 26, "vor": 50},
    ]


def test_simulation_uses_favorites_then_goalie_timing(tmp_path):
    m = owners.models(_con(tmp_path))
    ann = dict(m["Ann"], name="Ann")
    plan = [(23, ann, "adp"), (24, ann, "adp"), (25, None, "adp")]
    gone, log = owners.simulate(_pool(), plan)
    assert [x["full_name"] for _, _, x, _ in log] == ["Evan Bouchard", "Andrei Vasilevskiy", "Nick Suzuki"]
    assert [why for *_, why in log] == ["favorite", "first G", "adp"]


def test_simulation_skips_first_goalie_when_owner_already_has_one(tmp_path):
    m = owners.models(_con(tmp_path))
    ann = dict(m["Ann"], name="Ann")
    _, log = owners.simulate(_pool(), [(23, ann, "adp")], already={"Ann": {"G", "D"}})
    assert log[0][2]["full_name"] == "Evan Bouchard"  # favourite still wins
    _, log = owners.simulate([x for x in _pool() if x["full_name"] != "Evan Bouchard"], [(23, ann, "adp")], already={"Ann": {"G"}})
    assert log[0][3] == "adp"  # no second "first G"


def test_vona_returns_log_and_next_available(tmp_path):
    m = owners.models(_con(tmp_path))
    plan = [(23, dict(m["Ann"], name="Ann"), "adp"), (24, dict(m["Ann"], name="Ann"), "adp")]
    avail, nxt, log = rank.vona(_pool(), 2, {"F": 1, "D": 1, "G": 1}, plan=plan)
    assert len(log) == 2 and nxt["G"] == 30 and nxt["D"] == 0
    assert avail[0]["full_name"] in ("Evan Bouchard", "Andrei Vasilevskiy")


def test_summary_without_history(tmp_path):
    con = db.connect(tmp_path / "e.sqlite")
    assert "no draft history" in owners.summary(con, {})


def test_roster_shape_and_bench_spread():
    starters, bench, ir = rank.roster_shape({"C": 2, "LW": 2, "RW": 2, "UTIL": 1, "D": 4, "G": 2, "BE": 4, "IR": 1})
    assert starters == {"F": 7, "D": 4, "G": 2} and bench == 4 and ir == 1
    depth = rank.with_bench(starters, bench)
    assert sum(depth.values()) == 17 and depth["F"] >= depth["D"] >= depth["G"] and depth["G"] >= 2


def test_check_refuses_empty_league():
    import pytest
    with pytest.raises(SystemExit):
        rank.check({"teams": 0, "scoring": {}, "starters": {"F": 0, "D": 0, "G": 0}})


def test_build_refuses_without_league_pull(tmp_path):
    import pytest
    con = db.connect(tmp_path / "n.sqlite")
    with pytest.raises(SystemExit, match="League settings not loaded"):
        rank.build(con)


def test_skill_md_copies_match():
    root = Path(__file__).resolve().parent.parent
    assert (root / "SKILL.md").read_text() == (root / "skills/espn-draft-board/SKILL.md").read_text()
