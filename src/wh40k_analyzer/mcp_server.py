"""L5: stdio MCP server exposing roster loading and damage analysis.

Designed for local use from ZCode/Claude: the LLM client reads ability
texts via ``army_summary`` and composes scenarios from the catalog;
the engine stays deterministic.
"""

from __future__ import annotations

import random

from mcp.server.fastmcp import FastMCP

from wh40k_analyzer.engine.matrix import DEFAULT_TRIALS, damage_matrix, matrix_cell
from wh40k_analyzer.ingest.roster import load_roster
from wh40k_analyzer.model.army import Army
from wh40k_analyzer.report.text import army_header, full_report
from wh40k_analyzer.scenario.overlays import SCENARIOS, scenario_by_id, with_overrides

mcp = FastMCP("wh40k-analyzer")
_armies: dict[str, Army] = {}


@mcp.tool()
def load_roster_tool(path: str, roster_id: str) -> dict[str, object]:
    """Load a New Recruit roster JSON file and store it under roster_id.

    Returns a short summary: points, detachment, combat unit names.
    """
    army = load_roster(path)
    _armies[roster_id] = army
    return {
        "roster_id": roster_id,
        "name": army.name,
        "points": army.points_total,
        "detachment": army.detachment.name if army.detachment else None,
        "combat_units": [
            {
                "uid": u.uid,
                "name": u.name,
                "models": u.model_count,
                "wounds": u.wounds_total,
                "points": u.points,
                "attached": u.attached_names,
            }
            for u in army.combat_units
        ],
    }


@mcp.tool()
def army_summary(roster_id: str) -> str:
    """Full text summary of a loaded roster, including ability texts."""
    army = _armies.get(roster_id)
    if army is None:
        return f"roster '{roster_id}' not loaded; call load_roster_tool first"
    return army_header(army)


@mcp.tool()
def list_scenarios() -> dict[str, str]:
    """Catalog of available scenario overlays (id -> description)."""
    return {sid: desc for sid, (_, desc) in SCENARIOS.items()}


@mcp.tool()
def damage_matrix_tool(
    roster_a: str,
    roster_b: str,
    scenario: str = "base_shooting",
    half_range: bool = False,
    aura_plus1s: bool = False,
    forgefather_plus2s: bool = False,
    defender_strat: bool = False,
    trials: int = DEFAULT_TRIALS,
) -> str:
    """Mutual damage matrix between two loaded rosters as a text report."""
    army_a = _armies.get(roster_a)
    army_b = _armies.get(roster_b)
    if army_a is None or army_b is None:
        return "both rosters must be loaded first via load_roster_tool"
    base = scenario_by_id(scenario)
    overrides = {
        key: True
        for key, flag in [
            ("half_range", half_range),
            ("aura_plus1s_ranged", aura_plus1s),
            ("forgefather_plus2s", forgefather_plus2s),
            ("defender_strat_minus1ap", defender_strat),
        ]
        if flag
    }
    resolved = with_overrides(base, **overrides) if overrides else base
    matrix = damage_matrix(army_a, army_b, resolved, trials=trials, seed=None)
    description = SCENARIOS[scenario][1]
    if overrides:
        description += f" + {', '.join(overrides)}"
    return full_report(army_a, army_b, matrix["a_vs_b"], matrix["b_vs_a"], description)


@mcp.tool()
def duel(
    roster_a: str,
    unit_uid_a: str,
    roster_b: str,
    unit_uid_b: str,
    scenario: str = "base_shooting",
    trials: int = DEFAULT_TRIALS,
) -> str:
    """One attacker unit vs one defender unit under a scenario."""
    army_a = _armies.get(roster_a)
    army_b = _armies.get(roster_b)
    if army_a is None or army_b is None:
        return "both rosters must be loaded first via load_roster_tool"
    attacker = army_a.unit(unit_uid_a)
    defender = army_b.unit(unit_uid_b)
    if attacker is None or defender is None:
        return "unit uid not found; check combat_units in load_roster_tool output"
    resolved = scenario_by_id(scenario)
    cell = matrix_cell(attacker, defender, resolved, random.Random(), trials)
    return (
        f"{cell.attacker} → {cell.defender} ({cell.phase}):\n"
        f"  урон {cell.mean_wounds:.1f} из {cell.wounds_total} W "
        f"({cell.hp_fraction:.0%} HP)\n"
        f"  убито моделей {cell.mean_slain:.1f} из {cell.defender_models}\n"
        f"  P(уничтожить залпом) = {cell.p_destroy:.0%}"
    )


def run() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    run()
