"""CLI entry point: ``wh40k matrix|summary|mcp``."""

from __future__ import annotations

import argparse
import sys

from wh40k_analyzer.engine.matrix import DEFAULT_TRIALS, damage_matrix
from wh40k_analyzer.ingest.roster import load_roster
from wh40k_analyzer.report.text import army_header, full_report
from wh40k_analyzer.scenario.overlays import SCENARIOS, scenario_by_id, with_overrides


def __(key: str) -> str:  # small helper so --help stays readable
    return {
        "scenario_id": f"id сценария из: {', '.join(sorted(SCENARIOS))}",
    }[key]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wh40k", description="WH40k 11e list analyzer")
    sub = parser.add_subparsers(dest="command", required=True)

    p_matrix = sub.add_parser("matrix", help="взаимный урон двух ростеров")
    p_matrix.add_argument("roster_a")
    p_matrix.add_argument("roster_b")
    p_matrix.add_argument("--scenario", default="base_shooting", help=__("scenario_id"))
    p_matrix.add_argument("--half-range", action="store_true", help="половинная дальность")
    p_matrix.add_argument("--aura-1s", action="store_true", help="аура +1S стрельбы в 12″")
    p_matrix.add_argument("--forgefather-2s", action="store_true", help="+2S Melta/Torrent")
    p_matrix.add_argument("--def-strat", action="store_true", help="защитная стратагема −1 AP")
    p_matrix.add_argument("--trials", type=int, default=DEFAULT_TRIALS)
    p_matrix.add_argument("--seed", type=int, default=None)

    p_sum = sub.add_parser("summary", help="сводка одного ростера")
    p_sum.add_argument("roster")

    sub.add_parser("mcp", help="stdio MCP server")

    args = parser.parse_args(argv)

    if args.command == "summary":
        print(army_header(load_roster(args.roster)))
        return 0

    if args.command == "mcp":
        from wh40k_analyzer.mcp_server import run

        run()
        return 0

    base = scenario_by_id(args.scenario)
    scenario = with_overrides(
        base,
        **{
            key: True
            for key, flag in [
                ("half_range", args.half_range),
                ("aura_plus1s_ranged", args.aura_1s),
                ("forgefather_plus2s", args.forgefather_2s),
                ("defender_strat_minus1ap", args.def_strat),
            ]
            if flag
        },
    )
    army_a = load_roster(args.roster_a)
    army_b = load_roster(args.roster_b)
    matrix = damage_matrix(army_a, army_b, scenario, trials=args.trials, seed=args.seed)
    description = SCENARIOS[args.scenario][1]
    overrides = [
        k
        for k, v in vars(args).items()
        if k in {"half_range", "aura_1s", "forgefather_2s", "def_strat"} and v
    ]
    if overrides:
        description += f" + ручные флаги: {', '.join(overrides)}"
    print(full_report(army_a, army_b, matrix["a_vs_b"], matrix["b_vs_a"], description))
    return 0


if __name__ == "__main__":
    sys.exit(main())
