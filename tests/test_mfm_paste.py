"""MFM paste parser tests against the verified Death Guard paste."""

from pathlib import Path

import pytest

from wh40k_analyzer.ingest.mfm_paste import parse_mfm_paste

FIXTURE = Path(__file__).parent / "fixtures" / "mfm_dg_paste.txt"


@pytest.fixture
def doc():
    return parse_mfm_paste(FIXTURE.read_text(encoding="utf-8"))


def test_totals(doc):
    assert len(doc.units) == 36  # 30 UNITS + 6 PLAGUE LEGIONS
    assert len(doc.detachments) == 9


def test_leader_lists(doc):
    leaders = {u.name: u.leader_of for u in doc.units if u.leader_of}
    assert len(leaders) == 11
    assert leaders["BIOLOGUS PUTRIFIER"] == ["PLAGUE MARINES"]
    assert leaders["TYPHUS"] == [
        "BLIGHTLORD TERMINATORS",
        "DEATHSHROUD TERMINATORS",
        "POXWALKERS",
    ]


def test_bracket_pricing(doc):
    ds = next(u for u in doc.units if u.name == "DEATHSHROUD TERMINATORS")
    by_bracket: dict[str, list[int]] = {}
    for cost in ds.costs:
        by_bracket.setdefault(cost.bracket.split()[0], []).append(cost.pts)
    assert by_bracket["1ST"] == [150, 305]
    assert by_bracket["3RD"] == [160, 315]
    assert ds.costs[0].changed == "▼" and ds.costs[0].delta == -10


def test_wargear_options(doc):
    defiler = next(u for u in doc.units if u.name == "DEFILER")
    assert defiler.wargear == [
        {"item": "Heavy Reaper Autocannon", "pts": 15},
        {"item": "Hades Lascannon", "pts": 15},
    ]


def test_detachments_complete(doc):
    by_name = {d.name: d for d in doc.detachments}
    assert set(by_name) == {
        "CHAMPIONS OF CONTAGION",
        "CONTAGION ENGINES",
        "DEATH LORD’S CHOSEN",
        "FLYBLOWN HOST",
        "MORTARION’S HAMMER",
        "PARAGONS OF PUTRESCENCE",
        "SHAMBLEROT VECTORIUM",
        "TALLYBAND SUMMONERS",
        "VIRULENT VECTORIUM",
    }
    vv = by_name["VIRULENT VECTORIUM"]
    assert vv.dp == 3
    assert vv.roles == ["TAKE AND HOLD", "PURGE THE FOE"]
    assert all(e.pts is not None for e in vv.enhancements)
    assert len(vv.enhancements) == 4


def test_sections_split(doc):
    plague = [u for u in doc.units if u.section == "PLAGUE LEGIONS"]
    assert len(plague) == 6
    assert {u.name for u in plague} >= {"BEASTS OF NURGLE", "ROTIGUS"}
