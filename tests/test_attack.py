"""Attack engine tests: each keyword mechanic pinned against hand math.

Analytic expectations use fractions of d6 outcomes; Monte Carlo checks run
multiple independent seeds (the fixed-seed-in-loop bug from our simulation
sessions is exactly what these tests guard against).
"""

from __future__ import annotations

import random
from dataclasses import replace as dc_replace
from typing import Any

import pytest

from wh40k_analyzer.engine.attack import (
    AttackContext,
    AttackDie,
    DamageEvent,
    Target,
    TargetGroup,
    allocate,
    resolve_die,
)
from wh40k_analyzer.model.stats import DiceExpr, StatsLine

N_TRIALS = 40_000


def make_target(
    t: int = 4,
    sv: int | None = None,
    invuln: int | None = None,
    w: int = 1,
    count: int = 1,
    fnp: int | None = None,
    keywords: list[str] | None = None,
) -> Target:
    group = TargetGroup(stats=StatsLine(T=t, Sv=sv, W=w, invuln=invuln), count=count, fnp=fnp)
    return Target(groups=[group], keywords=keywords or [])


def die(**kwargs: Any) -> AttackDie:
    defaults: dict[str, Any] = dict(
        hit_target=3, S=4, AP=0, damage=DiceExpr(sides=None, modifier=1)
    )
    defaults.update(kwargs)
    return AttackDie(**defaults)


def mean_damage(atk: AttackDie, target: Target, ctx: AttackContext, n: int = N_TRIALS) -> float:
    """Mean wounds lost per die, FNP included (allocation against a big dummy
    group so that nothing is lost to overkill)."""
    rng = random.Random()
    sponge = Target(groups=[TargetGroup(stats=StatsLine(T=4, W=99, Sv=None), count=1)], keywords=[])
    fnp = target.groups[0].fnp
    sponge.groups[0].fnp = fnp
    total = 0
    for _ in range(n):
        events = resolve_die(atk, target, ctx, rng)
        total += allocate(events, sponge, rng).wounds_lost
    return total / n


# --- wound table ---


@pytest.mark.parametrize(
    "s,t,expected",
    [
        (8, 4, 2),  # S >= 2T
        (6, 4, 3),  # S > T
        (4, 4, 4),  # equal
        (3, 4, 5),  # S > T/2
        (2, 4, 6),  # S <= T/2 (2S == T)
        (8, 12, 5),  # our scythes vs Land Raider: 2*8 > 12
        (8, 16, 6),  # 2S == T
    ],
)
def test_wound_table(s, t, expected):
    from wh40k_analyzer.engine.dice import wound_target

    assert wound_target(s, t) == expected


# --- basic chain: hit 3+ x wound x save ---


def test_plain_chain_expectation():
    # hit 3+ (4/6), wound 4+ (3/6), no save, D1
    atk = die()
    target = make_target(t=4)
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx(4 / 6 * 3 / 6, abs=0.01)


def test_save_reduces_damage():
    # save 3+ -> fail 2/6
    atk = die()
    target = make_target(t=4, sv=3)
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx(4 / 6 * 3 / 6 * 2 / 6, abs=0.01)


def test_invuln_better_than_worsened_armor():
    # armor 2+ vs AP-2 -> 4+; invuln 4+ stays 4+ => fail 3/6 (Deathshroud case)
    atk = die(AP=-2)
    target = make_target(t=4, sv=2, invuln=4)
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx(4 / 6 * 3 / 6 * 3 / 6, abs=0.01)


def test_defensive_stratagem_shifts_ap():
    # AP-2 weakened to AP-1: armor 2+ -> 3+ (fail 2/6), better than invuln 4+
    atk = die(AP=-2)
    target = make_target(t=4, sv=2, invuln=4)
    got = mean_damage(atk, target, AttackContext(ap_shift=1))
    assert got == pytest.approx(4 / 6 * 3 / 6 * 2 / 6, abs=0.01)


# --- keywords ---


def test_torrent_auto_hits():
    atk = die(hit_target=None, S=5, AP=-1)  # flamer vs T5: wound 4+
    target = make_target(t=5)
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx(3 / 6, abs=0.01)


def test_melta_bonus_at_half_range():
    atk = die(S=10, AP=-3, damage=DiceExpr(sides=3, modifier=2), melta=3)
    target = make_target(t=10, sv=None)
    # S10 vs T10: 4+; D3+2 -> E=4; at half range +3 -> E=7
    far = mean_damage(atk, target, AttackContext())
    near = mean_damage(atk, target, AttackContext(half_range=True))
    assert far == pytest.approx(4 / 6 * 3 / 6 * 4, abs=0.02)
    assert near == pytest.approx(4 / 6 * 3 / 6 * 7, abs=0.03)


def test_sustained_hits_add_crit_hits():
    # BS 2+ (5/6, crit on 6 = 1/6): sustained 1 -> E[hits] = 5/6 + 1/6
    atk = die(hit_target=2, S=4, sustained=1)
    target = make_target(t=4)
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx((5 / 6 + 1 / 6) * 3 / 6, abs=0.01)


def test_sustained_condition_non_monster_vehicle():
    atk = die(hit_target=2, S=4, sustained=1, sustained_only_non_mv=True)
    infantry = mean_damage(atk, make_target(t=4, keywords=["Infantry"]), AttackContext())
    vehicle = mean_damage(atk, make_target(t=8, keywords=["Vehicle"]), AttackContext())
    assert infantry == pytest.approx((5 / 6 + 1 / 6) * 3 / 6, abs=0.01)
    # vs T8 vehicle: no sustained, S4 vs T8 wounds on 6+
    assert vehicle == pytest.approx(5 / 6 * 1 / 6, abs=0.01)


def test_lethal_hits_auto_wound_on_crit():
    # BS 2+: crit 1/6 auto-wounds; other hits wound 4+ vs T4
    atk = die(hit_target=2, S=4, lethal_hits=True)
    target = make_target(t=4)
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx(1 / 6 * 1 + 4 / 6 * 3 / 6, abs=0.01)


def test_devastating_wounds_mortal_on_crit_wound():
    # wound 4+ vs save 3+: crit-wound 1/6 -> D3 mortal bypassing save (E=2);
    # normal wounds 2/6 still roll the save (fail 2/6) for D3.
    # With devastating disabled this would be 4/6 * 3/6 * 2/6 * 2 = 0.148.
    atk = die(S=4, devastating_wounds=True, damage=DiceExpr(sides=3))
    target = make_target(t=4, sv=3)
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx(4 / 6 * (1 / 6 * 2 + 2 / 6 * 2 / 6 * 2), abs=0.01)


def test_twin_linked_rerolls_wounds():
    # wound 4+ (3/6), reroll fails: 3/6 + 3/6*3/6
    atk = die(S=4, twin_linked=True)
    target = make_target(t=4)
    got = mean_damage(atk, target, AttackContext())
    expected = 4 / 6 * (3 / 6 + 3 / 6 * 3 / 6)
    assert got == pytest.approx(expected, abs=0.01)


def test_anti_keyword_threshold():
    atk = die(S=4, anti_keyword="Infantry", anti_threshold=2)
    target = make_target(t=10, keywords=["Infantry"])  # base 6+ -> anti 2+
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx(4 / 6 * 5 / 6, abs=0.01)


def test_aura_s_bonuses():

    atk = dc_replace(die(S=5), is_melta_or_torrent=True)
    target = make_target(t=8)
    base = mean_damage(atk, target, AttackContext())
    buffed = mean_damage(
        atk, target, AttackContext(attacker_s_bonus=1, attacker_s_bonus_melta_torrent=2)
    )
    # S5 vs T8: 5+; S8 vs T8: 4+
    assert base == pytest.approx(4 / 6 * 2 / 6, abs=0.01)
    assert buffed == pytest.approx(4 / 6 * 3 / 6, abs=0.01)


def test_fnp_reduces_wounds():
    atk = die()
    target = make_target(t=4, fnp=5)  # 1/3 of lost wounds saved
    got = mean_damage(atk, target, AttackContext())
    assert got == pytest.approx(4 / 6 * 3 / 6 * 2 / 3, abs=0.01)


# --- allocation ---


def test_allocation_overkill_lost():
    # two attacks of 5 wounds vs two 4W models: 2 slain, 8 wounds lost total
    events = [DamageEvent(wounds=5), DamageEvent(wounds=5)]
    result = allocate(events, make_target(t=4, w=4, count=2), random.Random(1))
    assert result.models_slain == 2
    assert result.wounds_lost == 8
    assert result.destroyed


def test_allocation_wounded_model_finished_first():
    # first attack wounds a 4W model (3 lost), second deals 2: 1 kills it,
    # 1 is overkill -> 4 wounds lost, one model slain
    events = [DamageEvent(wounds=3), DamageEvent(wounds=2)]
    result = allocate(events, make_target(t=4, w=4, count=2), random.Random(1))
    assert result.models_slain == 1
    assert result.wounds_lost == 4


def test_allocation_bodyguard_before_characters():
    # two 1W bodyguard + one 1W character: 3 wounds kill all in order
    groups = [
        TargetGroup(stats=StatsLine(T=4, W=1), count=2),
        TargetGroup(stats=StatsLine(T=4, W=1), count=1, is_character=True),
    ]
    target = Target(groups=groups, keywords=[])
    result = allocate([DamageEvent(wounds=1)] * 3, target, random.Random(1))
    assert result.models_slain == 3
    assert result.destroyed


def test_mortal_batch_capped_to_one_model():
    # 6 mortal wounds vs 2W models: only one model dies, 4 MW lost
    events = [DamageEvent(wounds=6, mortal=True)]
    result = allocate(events, make_target(t=4, w=2, count=3), random.Random(1))
    assert result.models_slain == 1
    assert result.wounds_lost == 2


def test_lance_bonus_only_on_charge():
    """11e LANCE rule (roster text): +1 to wound if the unit charged this
    turn — NOT tied to Monster/Vehicle targets."""
    atk = die(S=8, AP=-2, lance=True, hit_target=3)
    infantry = make_target(t=10, keywords=["Infantry"])
    vehicle = make_target(t=10, keywords=["Vehicle"])
    ctx_plain = AttackContext()
    ctx_charge = AttackContext(attacker_charged=True)
    # uncharged: S8 vs T10 -> 5+, regardless of target type
    assert mean_damage(atk, infantry, ctx_plain) == pytest.approx(4 / 6 * 2 / 6, abs=0.01)
    assert mean_damage(atk, vehicle, ctx_plain) == pytest.approx(4 / 6 * 2 / 6, abs=0.01)
    # charged: 4+ vs any target
    assert mean_damage(atk, infantry, ctx_charge) == pytest.approx(4 / 6 * 3 / 6, abs=0.01)
    assert mean_damage(atk, vehicle, ctx_charge) == pytest.approx(4 / 6 * 3 / 6, abs=0.01)


def test_hunter_mode_selection():
    """HUNTER:Monster/Vehicle is an alternative profile, not an extra shot:
    one die per model, S12/BS2+ vs vehicles, S10/BS3+ vs everyone else."""
    from wh40k_analyzer.engine.attack import Target, plan_volley
    from wh40k_analyzer.model.army import CombatUnit, ModelProfile
    from wh40k_analyzer.model.weapons import WeaponMode, WeaponProfile

    rifle = WeaponProfile(
        name="Melta rifle",
        kind="ranged",
        modes=[
            WeaponMode(
                name="Melta Rifle HUNTER:Monster/Vehicle",
                kind="ranged",
                range_in=18,
                attacks=DiceExpr(sides=None, modifier=1),
                skill=2,
                S=12,
                AP=-3,
                damage=DiceExpr(sides=3, modifier=2),
                keywords=["Melta 2"],
            ),
            WeaponMode(
                name="Melta Rifle",
                kind="ranged",
                range_in=18,
                attacks=DiceExpr(sides=None, modifier=1),
                skill=3,
                S=10,
                AP=-3,
                damage=DiceExpr(sides=3, modifier=2),
                keywords=["Melta 2"],
            ),
        ],
    )
    unit = CombatUnit(
        uid="erad",
        name="Eradicator Squad",
        keywords=["Infantry"],
        models=[
            ModelProfile(
                name="Eradicator", count=3, stats=StatsLine(T=6, Sv=3, W=3), weapons=[rifle]
            )
        ],
    )
    rng = random.Random(1)
    vehicle = Target(
        groups=[TargetGroup(stats=StatsLine(T=10, Sv=3, W=12), count=1)],
        keywords=["Vehicle"],
    )
    infantry = Target(
        groups=[TargetGroup(stats=StatsLine(T=4, Sv=3, W=2), count=5)],
        keywords=["Infantry"],
    )
    plan_v = plan_volley(unit, "ranged", vehicle, AttackContext(), rng)
    plan_i = plan_volley(unit, "ranged", infantry, AttackContext(), rng)
    assert len(plan_v) == 1 and len(plan_i) == 1  # no double fire
    assert plan_v[0][0].S == 12 and plan_v[0][0].hit_target == 2
    assert plan_i[0][0].S == 10 and plan_i[0][0].hit_target == 3
    assert plan_v[0][1] == 3 and plan_i[0][1] == 3  # dice = 3 models x A1


def test_blast_dice_per_weapon_copy():
    """Regression: a model with 2 copies of a Blast 2 weapon vs 10 targets
    gathers 2x(4 + 2x2) = 16 dice, not 12 (per-cannon gather, not per entry)."""
    from wh40k_analyzer.engine.attack import Target, plan_volley
    from wh40k_analyzer.model.army import CombatUnit, ModelProfile
    from wh40k_analyzer.model.weapons import WeaponMode, WeaponProfile

    cannons = WeaponProfile(
        name="Flamestorm Cannon",
        kind="ranged",
        multiplicity=2,
        modes=[
            WeaponMode(
                name="Flamestorm Cannon",
                kind="ranged",
                range_in=12,
                attacks=DiceExpr(sides=None, modifier=4),
                skill=None,
                S=6,
                AP=-2,
                damage=DiceExpr(sides=None, modifier=2),
                keywords=["Blast 2", "Torrent"],
            )
        ],
    )
    unit = CombatUnit(
        uid="lr",
        name="Redeemer",
        keywords=["Vehicle"],
        models=[
            ModelProfile(name="LR", count=1, stats=StatsLine(T=12, Sv=2, W=16), weapons=[cannons])
        ],
    )
    target = Target(
        groups=[TargetGroup(stats=StatsLine(T=6, Sv=2, W=4, invuln=4), count=10)],
        keywords=["Infantry"],
    )
    plan = plan_volley(unit, "ranged", target, AttackContext(), random.Random(1))
    assert len(plan) == 1
    assert plan[0][1] == 16  # 2 cannons x (A4 + Blast2 x 2 brackets of 5)


def test_conditional_devastating_wounds_keyword():
    """'Devastating Wounds: non-Monster/Vehicle' (Redemptor gatling): mortal
    wounds bypass saves vs infantry, do NOT apply vs vehicles."""
    atk = dc_replace(
        die(S=6, damage=DiceExpr(sides=None, modifier=2)),
        devastating_wounds=True,
        devastating_only_non_mv=True,
    )
    infantry = make_target(t=4, sv=3, keywords=["Infantry"])  # wound 3+
    vehicle = make_target(t=8, sv=3, keywords=["Vehicle"])  # wound 5+
    # infantry: hit 4/6, crit-wound 1/6 -> 2 MW bypassing the 3+ save,
    # non-crit 3/6 must roll the save (fail 2/6)
    got_i = mean_damage(atk, infantry, AttackContext())
    assert got_i == pytest.approx(4 / 6 * (1 / 6 * 2 + 3 / 6 * 2 / 6 * 2), abs=0.01)
    # vehicle: DevW off, plain chain, wound 5+
    got_v = mean_damage(atk, vehicle, AttackContext())
    assert got_v == pytest.approx(4 / 6 * 2 / 6 * 2 / 6 * 2, abs=0.01)


def test_wrath_of_machine_spirit_context_flag():
    """The plan-level context flag grants conditional DevW to ranged volleys
    (Wrath of the Machine Spirit on the Land Raider Redeemer)."""
    from wh40k_analyzer.engine.attack import Target, TargetGroup, plan_volley
    from wh40k_analyzer.model.army import CombatUnit, ModelProfile
    from wh40k_analyzer.model.weapons import WeaponMode, WeaponProfile

    bolter = WeaponProfile(
        name="Bolter",
        kind="ranged",
        modes=[
            WeaponMode(
                name="Bolter",
                kind="ranged",
                range_in=24,
                attacks=DiceExpr(sides=None, modifier=1),
                skill=3,
                S=6,
                AP=0,
                damage=DiceExpr(sides=None, modifier=2),
                keywords=[],
            )
        ],
    )
    unit = CombatUnit(
        uid="tank",
        name="Tank",
        keywords=["Vehicle"],
        models=[
            ModelProfile(name="Tank", count=1, stats=StatsLine(T=12, Sv=2, W=16), weapons=[bolter])
        ],
    )
    infantry = Target(
        groups=[TargetGroup(stats=StatsLine(T=4, Sv=3, W=2), count=5)],
        keywords=["Infantry"],
    )
    rng = random.Random(1)
    plan_plain = plan_volley(unit, "ranged", infantry, AttackContext(), rng)
    plan_wrath = plan_volley(
        unit, "ranged", infantry, AttackContext(ranged_devastating_non_mv=True), rng
    )
    assert not plan_plain[0][0].devastating_wounds
    die_wrath = plan_wrath[0][0]
    assert die_wrath.devastating_wounds and die_wrath.devastating_only_non_mv
    # numeric: wrath die vs infantry matches the conditional DevW expectation
    got = mean_damage(die_wrath, infantry, AttackContext())
    assert got == pytest.approx(4 / 6 * (1 / 6 * 2 + 3 / 6 * 2 / 6 * 2), abs=0.01)
