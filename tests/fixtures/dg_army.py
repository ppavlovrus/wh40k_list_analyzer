"""Synthetic Death Guard army built from verified BSData 11e profiles.

Used by acceptance/integration tests: the engine and matrix are exercised
on the Salamanders-vs-DG matchup. Profiles are transcribed from
BSData/wh40k-11e (cross-checked with the official MFM paste fixture).
"""

from __future__ import annotations

from typing import Any

from wh40k_analyzer.model.army import Army, CombatUnit, ModelProfile
from wh40k_analyzer.model.stats import DiceExpr, StatsLine
from wh40k_analyzer.model.weapons import Kind, WeaponMode, WeaponProfile


def mode(name: str, kind: Kind, **kw: Any) -> WeaponMode:
    return WeaponMode(name=name, kind=kind, **kw)


def weapon(name: str, kind: Kind, modes: list[WeaponMode]) -> WeaponProfile:
    return WeaponProfile(name=name, kind=kind, modes=modes)


def model(name: str, count: int, stats: StatsLine, weapons: list[WeaponProfile]) -> ModelProfile:
    return ModelProfile(name=name, count=count, stats=stats, weapons=weapons)


def manreaper() -> WeaponProfile:
    """Strike/sweep scythe shared by Deathshrouds and the Lord of Contagion."""
    return weapon(
        "Manreaper",
        "melee",
        [
            mode(
                "strike",
                "melee",
                attacks=DiceExpr(sides=None, modifier=4),
                skill=2,
                S=8,
                AP=-2,
                damage=DiceExpr(sides=None, modifier=2),
                keywords=["Lethal Hits"],
            ),
            mode(
                "sweep",
                "melee",
                attacks=DiceExpr(sides=None, modifier=8),
                skill=3,
                S=4,
                AP=-1,
                damage=DiceExpr(sides=None, modifier=1),
                keywords=["Lethal Hits"],
            ),
        ],
    )


def _with_lance(weapon: WeaponProfile) -> WeaponProfile:
    """The attached Lord of Contagion grants [LANCE] to the unit's melee
    weapons (user-confirmed ruling); bare Deathshrouds have no Lance."""
    cloned = weapon.model_copy(deep=True)
    for mode in cloned.modes:
        mode.keywords = [*mode.keywords, "Lance"]
    return cloned


def shrouds_unit(count: int = 6, with_lord: bool = True) -> CombatUnit:
    models = [
        model(
            "Deathshroud Terminator",
            count,
            StatsLine(T=7, Sv=2, W=4, invuln=4),
            [
                # Plaguespurt gauntlet: Torrent pistol, kept for completeness
                weapon(
                    "Plaguespurt gauntlet",
                    "ranged",
                    [
                        mode(
                            "Plaguespurt gauntlet",
                            "ranged",
                            range_in=12,
                            attacks=DiceExpr(sides=6),
                            skill=None,
                            S=3,
                            AP=0,
                            damage=DiceExpr(sides=None, modifier=1),
                            keywords=["Anti-Infantry 4+", "Ignores Cover", "Pistol", "Torrent"],
                        )
                    ],
                ),
                manreaper(),
            ],
        )
    ]
    if with_lord:
        # LANCE aura from the lord covers the whole attached unit
        models[0].weapons[1] = _with_lance(models[0].weapons[1])
        models.append(
            model(
                "Lord of Contagion",
                1,
                StatsLine(T=7, Sv=2, W=6, invuln=4),
                # Lord's scythe: strike S9 D3 A5, sweep S6 D1 A10
                [
                    weapon(
                        "Manreaper",
                        "melee",
                        [
                            mode(
                                "strike",
                                "melee",
                                attacks=DiceExpr(sides=None, modifier=5),
                                skill=2,
                                S=9,
                                AP=-2,
                                damage=DiceExpr(sides=3, modifier=0),
                                keywords=["Lethal Hits"],
                            ),
                            mode(
                                "sweep",
                                "melee",
                                attacks=DiceExpr(sides=None, modifier=10),
                                skill=2,
                                S=6,
                                AP=-1,
                                damage=DiceExpr(sides=None, modifier=1),
                                keywords=["Lethal Hits"],
                            ),
                        ],
                    )
                ],
            )
        )
    return CombatUnit(
        uid=f"dg-shrouds-{count}",
        name="Deathshroud Terminators",
        role="Infantry",
        keywords=["Infantry", "Chaos", "Nurgle", "Terminator"],
        models=models,
        points=305 + (110 if with_lord else 0),
    )


def blightlords_unit() -> CombatUnit:
    return CombatUnit(
        uid="dg-blightlords",
        name="Blightlord Terminators",
        role="Infantry",
        keywords=["Infantry", "Chaos", "Nurgle", "Terminator"],
        models=[
            model(
                "Blightlord Terminator",
                10,
                StatsLine(T=7, Sv=2, W=3, invuln=4),
                [
                    weapon(
                        "Combi-bolter",
                        "ranged",
                        [
                            mode(
                                "Combi-bolter",
                                "ranged",
                                range_in=24,
                                attacks=DiceExpr(sides=None, modifier=4),
                                skill=3,
                                S=5,
                                AP=-1,
                                damage=DiceExpr(sides=None, modifier=1),
                                keywords=["Rapid Fire 2"],
                            )
                        ],
                    ),
                    manreaper(),
                ],
            )
        ],
        points=370,
    )


def plagueburst_crawler() -> CombatUnit:
    return CombatUnit(
        uid="dg-pbc",
        name="Plagueburst Crawler",
        role="Vehicle",
        keywords=["Vehicle", "Chaos", "Nurgle"],
        models=[
            model(
                "Plagueburst Crawler",
                1,
                StatsLine(T=10, Sv=2, W=12, invuln=5),
                [
                    weapon(
                        "Plagueburst mortar",
                        "ranged",
                        [
                            mode(
                                "Plagueburst mortar",
                                "ranged",
                                range_in=48,
                                attacks=DiceExpr(sides=6, modifier=3),
                                skill=3,
                                S=8,
                                AP=-1,
                                damage=DiceExpr(sides=None, modifier=2),
                                keywords=["Blast", "Indirect Fire", "Lethal Hits"],
                            )
                        ],
                    ),
                    weapon(
                        "Entropy cannon",
                        "ranged",
                        [
                            mode(
                                "Entropy cannon",
                                "ranged",
                                range_in=36,
                                attacks=DiceExpr(sides=None, modifier=1),
                                skill=3,
                                S=10,
                                AP=-3,
                                damage=DiceExpr(sides=6, modifier=1),
                                keywords=["Lethal Hits"],
                            )
                        ],
                    ),
                    weapon(
                        "Armoured Hull",
                        "melee",
                        [
                            mode(
                                "Armoured Hull",
                                "melee",
                                attacks=DiceExpr(sides=None, modifier=6),
                                skill=3,
                                S=8,
                                AP=-1,
                                damage=DiceExpr(sides=None, modifier=2),
                                keywords=[],
                            )
                        ],
                    ),
                ],
            )
        ],
        points=170,
    )


def blight_drone(uid: str) -> CombatUnit:
    return CombatUnit(
        uid=uid,
        name="Foetid Bloat-drone",
        role="Vehicle",
        keywords=["Vehicle", "Fly", "Chaos", "Nurgle"],
        models=[
            model(
                "Foetid Bloat-drone",
                1,
                StatsLine(T=9, Sv=3, W=10, invuln=5),
                [
                    weapon(
                        "Plaguespitter",
                        "ranged",
                        [
                            mode(
                                "Plaguespitter",
                                "ranged",
                                range_in=12,
                                attacks=DiceExpr(sides=6),
                                skill=None,
                                S=6,
                                AP=-1,
                                damage=DiceExpr(sides=None, modifier=1),
                                keywords=["Anti-Infantry 2+", "Ignores Cover", "Torrent"],
                            )
                        ],
                    ),
                    weapon(
                        "Fleshmower",
                        "melee",
                        [
                            mode(
                                "Fleshmower",
                                "melee",
                                attacks=DiceExpr(sides=None, modifier=10),
                                skill=3,
                                S=7,
                                AP=-1,
                                damage=DiceExpr(sides=None, modifier=2),
                                keywords=["Lethal Hits"],
                            )
                        ],
                    ),
                ],
            )
        ],
        points=100,
    )


def dg_army() -> Army:
    """The synthetic DG list from the matchup analysis."""
    return Army(
        name="Death Guard (synthetic)",
        faction="Chaos - Death Guard",
        points_total=sum(
            u.points
            for u in [
                shrouds_unit(6),
                blightlords_unit(),
                plagueburst_crawler(),
                blight_drone("dg-drone-1"),
                blight_drone("dg-drone-2"),
            ]
        ),
        combat_units=[
            shrouds_unit(6),
            blightlords_unit(),
            plagueburst_crawler(),
            blight_drone("dg-drone-1"),
            blight_drone("dg-drone-2"),
        ],
        source_file="<synthetic>",
    )
