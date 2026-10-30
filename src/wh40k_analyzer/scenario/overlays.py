"""L3: curated modifier catalog and Scenario overlay.

The engine is deterministic; all situational rules (auras, stratagems,
range brackets) are expressed here as explicit toggles the user selects.
The catalog entries mirror the Salamanders vs Death Guard meta the numbers
were hand-validated against; new entries are cheap to add.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from wh40k_analyzer.engine.attack import AttackContext
from wh40k_analyzer.model.weapons import Kind


@dataclass(frozen=True)
class Scenario:
    """One battle situation applied on top of the canonical model."""

    phase: Kind = "ranged"
    half_range: bool = False  # within half weapon range: Melta / Rapid Fire
    aura_plus1s_ranged: bool = False  # Vulkan's Quest: +1S ranged in 12"
    forgefather_plus2s: bool = False  # Vulkan He'stan: +2S Melta/Torrent, 24"
    defender_strat_minus1ap: bool = False  # defensive stratagem: AP -1 incoming
    charged: bool = False  # melee context (charge bonuses hook in later)
    wrath_of_machine_spirit: bool = False  # LR Redeemer: ranged DevW in 12" (non-MV)

    def context(self) -> AttackContext:
        return AttackContext(
            half_range=self.half_range,
            attacker_s_bonus=1 if self.aura_plus1s_ranged and self.phase == "ranged" else 0,
            attacker_s_bonus_melta_torrent=(
                2 if self.forgefather_plus2s and self.phase == "ranged" else 0
            ),
            ap_shift=1 if self.defender_strat_minus1ap else 0,
            attacker_charged=self.charged,
            ranged_devastating_non_mv=self.wrath_of_machine_spirit and self.phase == "ranged",
        )


# Curated catalog: id -> (Scenario, human description for reports)
SCENARIOS: dict[str, tuple[Scenario, str]] = {
    "base_shooting": (
        Scenario(phase="ranged"),
        "Стрельба, базовые профили, без аур и стратагем",
    ),
    "full_buffs_shooting": (
        Scenario(
            phase="ranged",
            half_range=True,
            aura_plus1s_ranged=True,
            forgefather_plus2s=True,
        ),
        "Стрельба: половинная дальность + аура +1S в 12″ (Vulkan's Quest) "
        "+ Forgefather +2S по цели (Melta/Torrent)",
    ),
    "half_range_shooting": (
        Scenario(phase="ranged", half_range=True),
        "Стрельба с половинной дальности (Melta/Rapid Fire активны), без аур",
    ),
    "melee": (Scenario(phase="melee"), "Мили, базовые профили, без чарджа"),
    "melee_charge": (
        Scenario(phase="melee", charged=True),
        "Мили в ход чарджа (LANCE-оружие ранит на +1)",
    ),
    "melee_charge_defensive_strat": (
        Scenario(phase="melee", charged=True, defender_strat_minus1ap=True),
        "Мили в ход чарджа, у защитника стратагема −1 AP входящим",
    ),
    "melee_defensive_strat": (
        Scenario(phase="melee", defender_strat_minus1ap=True),
        "Мили, у защитника стратагема −1 AP входящим",
    ),
    "shooting_defensive_strat": (
        Scenario(phase="ranged", defender_strat_minus1ap=True),
        "Стрельба, у защитника стратагема −1 AP входящим",
    ),
}


def scenario_by_id(scenario_id: str) -> Scenario:
    if scenario_id not in SCENARIOS:
        known = ", ".join(sorted(SCENARIOS))
        msg = f"unknown scenario '{scenario_id}'; known: {known}"
        raise KeyError(msg)
    return SCENARIOS[scenario_id][0]


def with_overrides(base: Scenario, **overrides: bool | str) -> Scenario:
    """Apply explicit CLI/MCP toggles on top of a catalog scenario."""
    return replace(base, **overrides)  # type: ignore[arg-type]
