"""Roster parser tests against the real Salamanders list."""

from pathlib import Path

import pytest

from wh40k_analyzer.ingest.roster import load_roster

FIXTURE = Path(__file__).parent / "fixtures" / "salamanders_take_and_hold.json"


@pytest.fixture
def army():
    return load_roster(FIXTURE)


def test_army_totals(army):
    assert army.points_total == 1960
    assert army.points_limit == 2000
    assert army.detachment is not None
    assert army.detachment.name == "Take and Hold"


def test_fielded_units_resolved_to_combat_units(army):
    # 13 raw selections; 4 attachments merge away -> 9 combat units.
    assert len(army.combat_units) == 9
    names = sorted(u.name for u in army.combat_units)
    assert "Infernus Squad" in names
    assert "Terminator Assault Squad" in names
    assert "Vulkan He'stan" not in names  # merged into Infernus Squad


def test_attachments_merged(army):
    infernus = next(u for u in army.combat_units if u.name == "Infernus Squad")
    assert set(infernus.attached_names) == {"Vulkan He'stan", "Ancient"}
    # 9 marines + 1 sergeant + Vulkan + Ancient
    assert infernus.model_count == 12
    characters = [m for m in infernus.models if m.is_character]
    assert len(characters) == 2

    terminators = next(u for u in army.combat_units if u.name == "Terminator Assault Squad")
    assert set(terminators.attached_names) == {
        "Chaplain in Terminator Armour",
        "Ancient in Terminator Armour",
    }


def test_unit_stats_and_weapons(army):
    infernus = next(u for u in army.combat_units if u.name == "Infernus Squad")
    marine = next(m for m in infernus.models if m.name == "Infernus Marines")
    assert marine.count == 9
    assert marine.stats is not None
    assert marine.stats.T == 5
    assert marine.stats.Sv == 3
    assert marine.stats.W == 2

    pyre = next(w for _, w in infernus.all_weapons() if w.name == "Pyreblaster")
    assert pyre.kind == "ranged"
    assert len(pyre.modes) == 1
    mode = pyre.modes[0]
    assert mode.attacks.expected == 4.0
    assert mode.S == 5
    assert mode.AP == -1
    assert mode.has_keyword("Torrent")
    assert mode.has_keyword("Blast")


def test_vehicle_unit(army):
    valiants = [u for u in army.combat_units if u.name == "Gladiator Valiant"]
    assert len(valiants) == 2  # duplicates distinguished by instance uid
    assert len({u.uid for u in valiants}) == 2
    assert valiants[0].role == "Vehicle"
    melta = next(w for _, w in valiants[0].all_weapons() if "melta" in w.name.lower())
    assert melta.modes[0].S == 10
    assert melta.modes[0].damage is not None
    assert melta.modes[0].damage.expected == pytest.approx(2.0 + 2)  # D3+2
    assert melta.modes[0].keyword_value("Melta") == 3


def test_alternative_weapon_modes_parsed(army):
    lt = next(u for u in army.combat_units if u.name == "Lieutenant with Combi-weapon")
    combi = next(w for _, w in lt.all_weapons() if w.name == "Combi-weapon")
    mode_names = {m.name for m in combi.modes}
    assert any("Bolter" in n for n in mode_names)
    assert any("Flamer" in n for n in mode_names)


def test_abilities_captured(army):
    infernus = next(u for u in army.combat_units if u.name == "Infernus Squad")
    ability_names = {a.name for a in infernus.abilities}
    assert "Driven from Cover" in ability_names
    forgefather = [a for a in infernus.abilities if a.name == "Forgefather"]
    assert forgefather and "Melta" in forgefather[0].description


def test_nested_wargear_container_recursion(army):
    """Regression: weapons wrapped in container selections (critic finding)."""
    terminators = next(u for u in army.combat_units if u.name == "Terminator Assault Squad")
    sergeant = next(m for m in terminators.models if "Sergeant" in m.name)
    weapon_names = [w.name for w in sergeant.weapons]
    assert weapon_names, "sergeant lost weapons inside nested wargear container"
    marines = next(m for m in terminators.models if m.count == 9)
    assert any(w.name == "Thunder Hammer" for w in marines.weapons)


def test_merged_abilities_deduplicated(army):
    """Regression: leader abilities must not duplicate target's own (critic finding)."""
    for unit in army.combat_units:
        names = [a.name for a in unit.abilities]
        assert len(names) == len(set(names)), f"duplicate abilities in {unit.name}: {names}"
