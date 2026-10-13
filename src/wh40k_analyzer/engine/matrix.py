"""L4: mutual damage matrix — Monte Carlo over combat unit pairs."""

from __future__ import annotations

import random
from dataclasses import dataclass

from wh40k_analyzer.engine.attack import simulate_volley
from wh40k_analyzer.model.army import Army, CombatUnit
from wh40k_analyzer.scenario.overlays import Scenario

DEFAULT_TRIALS = 20_000


@dataclass(frozen=True)
class Cell:
    """One attacker x defender measurement of a volley."""

    attacker: str
    defender: str
    phase: str
    mean_wounds: float
    wounds_total: int
    mean_slain: float
    defender_models: int
    p_destroy: float

    @property
    def hp_fraction(self) -> float:
        return self.mean_wounds / self.wounds_total if self.wounds_total else 0.0


def matrix_cell(
    attacker: CombatUnit,
    defender: CombatUnit,
    scenario: Scenario,
    rng: random.Random,
    trials: int = DEFAULT_TRIALS,
) -> Cell:
    wounds = slain = destroyed = 0
    target = defender
    for _ in range(trials):
        result = simulate_volley(attacker, target, scenario.phase, scenario.context(), rng)
        wounds += result.wounds_lost
        slain += result.models_slain
        destroyed += result.destroyed
    return Cell(
        attacker=attacker.name,
        defender=defender.name,
        phase=scenario.phase,
        mean_wounds=wounds / trials,
        wounds_total=target.wounds_total,
        mean_slain=slain / trials,
        defender_models=target.model_count,
        p_destroy=destroyed / trials,
    )


def damage_matrix(
    army_a: Army,
    army_b: Army,
    scenario: Scenario,
    trials: int = DEFAULT_TRIALS,
    seed: int | None = None,
) -> dict[str, list[Cell]]:
    """Every unit of A shoots/fights every unit of B and vice versa."""
    base_rng = random.Random(seed)
    out: dict[str, list[Cell]] = {"a_vs_b": [], "b_vs_a": []}
    for attacker in army_a.combat_units:
        for defender in army_b.combat_units:
            out["a_vs_b"].append(matrix_cell(attacker, defender, scenario, base_rng, trials))
    for attacker in army_b.combat_units:
        for defender in army_a.combat_units:
            out["b_vs_a"].append(matrix_cell(attacker, defender, scenario, base_rng, trials))
    return out
