"""Attack resolution: hit -> wound -> save -> FNP -> damage -> allocation.

Semantics follow the 11e rule texts embedded in roster exports; every
keyword mechanic here is pinned by tests in ``tests/test_attack.py``.

Documented MVP assumptions:
- Critical results are unmodified 6s only; modifiers never create crits.
- Torrent weapons auto-hit (no hit roll, hence no critical hits).
- Lethal Hits: a critical hit wounds automatically (not a critical wound).
- Devastating Wounds: a critical wound inflicts D mortal wounds bypassing
  the save, damaging at most one model (leftover mortal wounds are lost).
- Wound rolls use the majority bodyguard group's Toughness.
- Blast/Cleave add dice to the weapon's total pool: X per 5 defender models.
- Damage allocation is greedy: each attack damages the current (wounded)
  model; overkill is lost; bodyguard models die before characters.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass

from wh40k_analyzer.engine.dice import d6, failed_save_target, is_crit, passes, wound_target
from wh40k_analyzer.model.army import CombatUnit, ModelProfile
from wh40k_analyzer.model.stats import DiceExpr, StatsLine
from wh40k_analyzer.model.weapons import Kind, WeaponMode, WeaponProfile

_MONSTER_VEHICLE = ("monster", "vehicle")
_FNP_RE = re.compile(r"Feel No Pain (\d)\+", re.IGNORECASE)


@dataclass(frozen=True)
class AttackContext:
    """Situational modifiers shared by one volley (built by Scenario in L3)."""

    half_range: bool = False  # within half weapon range: Melta / Rapid Fire
    attacker_s_bonus: int = 0  # blanket +S aura (e.g. +1S in 12")
    attacker_s_bonus_melta_torrent: int = 0  # Vulkan He'stan: +2S Melta/Torrent
    ap_shift: int = 0  # defensive stratagem: incoming AP magnitude reduced by 1
    hit_mod: int = 0
    wound_mod: int = 0
    attacker_charged: bool = False  # LANCE weapons wound at +1 this turn


@dataclass(frozen=True)
class AttackDie:
    """Parameters shared by the dice of one weapon mode volley."""

    hit_target: int | None  # BS/WS; None = auto-hit (Torrent)
    S: int
    AP: int  # negative, e.g. -2
    damage: DiceExpr
    melta: int = 0  # +damage at half range
    lethal_hits: bool = False
    devastating_wounds: bool = False
    sustained: int = 0
    sustained_only_non_mv: bool = False  # "non-Monster/Vehicle" condition
    twin_linked: bool = False  # re-roll failed wounds once
    anti_keyword: str | None = None  # Anti-X vs defender keyword
    anti_threshold: int | None = None
    lance: bool = False  # +1 to wound vs Monster/Vehicle
    is_melta_or_torrent: bool = False  # eligible for the Forgefather +2S aura

    @classmethod
    def from_mode(cls, mode: WeaponMode) -> AttackDie:
        kw = mode.keywords
        sustained_n = mode.keyword_value("Sustained Hits")
        melta_n = mode.keyword_value("Melta")
        anti_kw, anti_thr = _parse_anti(kw)
        return cls(
            hit_target=None if mode.has_keyword("Torrent") else mode.skill,
            S=mode.S or 0,
            AP=mode.AP,
            damage=mode.damage or DiceExpr(sides=None, modifier=1),
            melta=melta_n or 0,
            lethal_hits=mode.has_keyword("Lethal Hits"),
            devastating_wounds=mode.has_keyword("Devastating Wounds"),
            sustained=sustained_n or 0,
            sustained_only_non_mv=any(
                k.lower().startswith("sustained hits") and "non-monster" in k.lower() for k in kw
            ),
            twin_linked=mode.has_keyword("Twin-linked"),
            anti_keyword=anti_kw,
            anti_threshold=anti_thr,
            lance=mode.has_keyword("Lance"),
            is_melta_or_torrent=mode.has_keyword("Melta") or mode.has_keyword("Torrent"),
        )


def _parse_anti(keywords: list[str]) -> tuple[str | None, int | None]:
    for kw in keywords:
        m = re.match(r"^Anti-([A-Z/ ]+?)\s*(\d)\+$", kw, re.IGNORECASE)
        if m:
            return m.group(1).strip(), int(m.group(2))
    return None, None


@dataclass(frozen=True)
class DamageEvent:
    """One damaging hit: ``wounds`` lost unless saved by FNP; ``mortal``
    batches bypass saves and are capped to a single model."""

    wounds: int
    mortal: bool = False


@dataclass
class TargetGroup:
    stats: StatsLine
    count: int
    fnp: int | None = None
    is_character: bool = False

    @property
    def hp(self) -> int:
        return (self.stats.W or 1) * self.count


@dataclass
class Target:
    """Defender snapshot: model groups (bodyguard first), union keywords."""

    groups: list[TargetGroup]
    keywords: list[str]

    @classmethod
    def from_combat_unit(cls, unit: CombatUnit) -> Target:
        fnp_unit: int | None = None
        for ability in unit.abilities:
            m = _FNP_RE.search(ability.name)
            if m and (fnp_unit is None or int(m.group(1)) < fnp_unit):
                fnp_unit = int(m.group(1))
        groups = [
            TargetGroup(
                stats=m.stats,
                count=m.count,
                fnp=fnp_unit,
                is_character=m.is_character,
            )
            for m in unit.models
            if m.stats is not None
        ]
        bodyguard = [g for g in groups if not g.is_character]
        characters = [g for g in groups if g.is_character]
        return cls(groups=bodyguard + characters, keywords=list(unit.keywords))

    @property
    def model_count(self) -> int:
        return sum(g.count for g in self.groups)

    @property
    def wounds_total(self) -> int:
        return sum(g.hp for g in self.groups)

    @property
    def majority_toughness(self) -> int:
        if not self.groups:
            return 4
        biggest = max(self.groups, key=lambda g: g.count)
        return biggest.stats.T or 4

    def has_keyword(self, keyword: str) -> bool:
        lowered = keyword.lower()
        return any(
            k.lower() == lowered or k.lower().endswith(f": {lowered}") for k in self.keywords
        )

    @property
    def is_monster_or_vehicle(self) -> bool:
        return any(k.lower() in _MONSTER_VEHICLE for k in self.keywords)


def _sustained_applies(atk: AttackDie, target: Target) -> bool:
    return not (atk.sustained_only_non_mv and target.is_monster_or_vehicle)


def resolve_die(
    atk: AttackDie, target: Target, ctx: AttackContext, rng: random.Random
) -> list[DamageEvent]:
    """Resolve one attack die into damage events (sustained hits may add more)."""
    # --- hit ---
    crit_hit = False
    if atk.hit_target is None:  # Torrent: auto-hit, never critical
        n_hits = 1
    else:
        roll = d6(rng)
        if not passes(roll, atk.hit_target, ctx.hit_mod):
            return []
        crit_hit = is_crit(roll)
        n_hits = 1
        if crit_hit and atk.sustained and _sustained_applies(atk, target):
            n_hits += atk.sustained  # extra hits are plain, non-critical

    s_eff = atk.S + ctx.attacker_s_bonus
    if atk.is_melta_or_torrent:
        s_eff += ctx.attacker_s_bonus_melta_torrent

    # The die itself may auto-wound via Lethal Hits; sustained extras may not.
    events = []
    for idx in range(n_hits):
        auto_wound = crit_hit and atk.lethal_hits and idx == 0
        event = _one_hit(atk, target, ctx, rng, s_eff, auto_wound)
        if event is not None:
            events.append(event)
    return events


def _one_hit(
    atk: AttackDie,
    target: Target,
    ctx: AttackContext,
    rng: random.Random,
    s_eff: int,
    auto_wound: bool,
) -> DamageEvent | None:
    # --- wound ---
    if auto_wound:
        crit_wound = False
    else:
        t = wound_target(s_eff, target.majority_toughness)
        if atk.anti_keyword and atk.anti_threshold and target.has_keyword(atk.anti_keyword):
            t = min(t, atk.anti_threshold)
        if atk.lance and ctx.attacker_charged:
            t = max(2, t - 1)
        roll = d6(rng)
        if not passes(roll, t, ctx.wound_mod):
            if atk.twin_linked:  # re-roll failed wounds once
                roll = d6(rng)
                if not passes(roll, t, ctx.wound_mod):
                    return None
            else:
                return None
        crit_wound = is_crit(roll)

    # --- save ---
    if crit_wound and atk.devastating_wounds:
        dmg = atk.damage.roll(rng)
        return DamageEvent(wounds=dmg, mortal=True)

    ap_mag = max(0, -atk.AP - ctx.ap_shift)
    armor_eff = target.groups[0].stats.Sv
    best_save = None
    if armor_eff is not None:
        armor_eff = max(armor_eff + ap_mag, 2)
        best_save = armor_eff
    invuln = target.groups[0].stats.invuln
    if invuln is not None and (best_save is None or invuln < best_save):
        best_save = invuln
    if best_save is not None:
        roll = d6(rng)
        if passes(roll, best_save):
            return None

    dmg = atk.damage.roll(rng)
    if atk.melta and ctx.half_range:
        dmg += atk.melta
    return DamageEvent(wounds=dmg)


@dataclass
class AllocationResult:
    wounds_lost: int
    models_slain: int
    destroyed: bool


def allocate(events: list[DamageEvent], target: Target, rng: random.Random) -> AllocationResult:
    """Apply damage events greedily; overkill is lost; bodyguard dies first."""
    live = [g for g in target.groups if g.count > 0]
    queue = [[g.stats.W or 1] * g.count for g in live]
    fnp_by_group = [g.fnp for g in live]

    gi, mi = 0, 0  # current group / model index within group
    wounds_lost = 0
    models_slain = 0

    for ev in events:
        # FNP per wound, using the current model's group FNP
        fnp = fnp_by_group[gi] if gi < len(fnp_by_group) else None
        lost = 0
        for _ in range(ev.wounds):
            if fnp is not None and passes(d6(rng), fnp):
                continue
            lost += 1
        if lost == 0:
            continue
        # damage the current model only; overflow (all mortal overflow) is lost
        if gi < len(queue):
            hp = queue[gi][mi]
            take = min(lost, hp)
            queue[gi][mi] = hp - take
            wounds_lost += take
            if queue[gi][mi] == 0:
                models_slain += 1
                if mi + 1 < len(queue[gi]):
                    mi += 1
                else:
                    gi, mi = gi + 1, 0

    destroyed = all(hp == 0 for group in queue for hp in group)
    return AllocationResult(wounds_lost=wounds_lost, models_slain=models_slain, destroyed=destroyed)


def plan_volley(
    attacker: CombatUnit,
    phase: Kind,
    target: Target,
    ctx: AttackContext,
    rng: random.Random,
) -> list[tuple[AttackDie, int]]:
    """Build (die template, dice count) pairs for a whole unit volley.

    Ranged: every mode of every ranged weapon fires. Melee: weapons with
    alternative modes (strike/sweep) use the mode with the higher expected
    damage against this target.
    """
    out: list[tuple[AttackDie, int]] = []
    target_models = target.model_count
    for model in attacker.models:
        for weapon in model.weapons:
            if weapon.kind != phase:
                continue
            modes = weapon.modes
            if not modes:
                continue
            if phase == "melee" and len(modes) > 1:
                modes = [_best_melee_mode(modes, target)]
            if phase == "ranged" and len(modes) > 1 and any("HUNTER:" in m.name for m in modes):
                modes = [_select_hunter_mode(modes, target)]
            for mode in modes:
                die = AttackDie.from_mode(mode)
                dice = _mode_dice(mode, model, weapon, target_models, ctx, rng)
                out.append((die, dice))
    return out


def _mode_dice(
    mode: WeaponMode,
    model: ModelProfile,
    weapon: WeaponProfile,
    target_models: int,
    ctx: AttackContext,
    rng: random.Random,
) -> int:
    """Total dice for this mode: per-model rolls x copies, Blast/Cleave/Rapid Fire."""
    if mode.attacks is None:
        return 0
    per_model = mode.attacks.roll(rng)
    if ctx.half_range and mode.has_keyword("Rapid Fire"):
        per_model += mode.keyword_value("Rapid Fire") or 1
    total = model.count * weapon.multiplicity * per_model
    blast = mode.keyword_value("Blast") or (1 if mode.has_keyword("Blast") else 0)
    cleave = mode.keyword_value("Cleave") or (1 if mode.has_keyword("Cleave") else 0)
    extra_per_five = max(blast, cleave)
    if extra_per_five and target_models >= 5:
        # Blast dice are gathered per weapon copy, not per weapon entry
        total += weapon.multiplicity * extra_per_five * (target_models // 5)
    return total


def _select_hunter_mode(modes: list[WeaponMode], target: Target) -> WeaponMode:
    """HUNTER:X/Y modes are alternative profiles of the same weapon: the
    hunter profile replaces the base one against matching targets."""
    hunter = next(m for m in modes if "HUNTER:" in m.name)
    base = next((m for m in modes if "HUNTER:" not in m.name), hunter)
    keywords = hunter.name.split("HUNTER:", 1)[1]
    wanted = {k.strip().lower() for k in keywords.split("/")}
    matches = any(
        k.lower() == w or k.lower().endswith(f": {w}") for k in target.keywords for w in wanted
    )
    return hunter if matches else base


def _best_melee_mode(modes: list[WeaponMode], target: Target) -> WeaponMode:
    def rough(mode: WeaponMode) -> float:
        if mode.attacks is None or mode.damage is None or not mode.S:
            return -1.0
        hit_p = (7 - (mode.skill or 4)) / 6 if mode.skill else 1.0
        wound_p = (7 - wound_target(mode.S, target.majority_toughness)) / 6
        stats = target.groups[0].stats if target.groups else None
        save_fail = failed_save_target(stats.Sv, stats.invuln, max(0, -mode.AP)) if stats else 1.0
        return mode.attacks.expected * hit_p * wound_p * mode.damage.expected * save_fail

    return max(modes, key=rough)


def simulate_volley(
    attacker: CombatUnit,
    target_unit: CombatUnit,
    phase: Kind,
    ctx: AttackContext,
    rng: random.Random,
) -> AllocationResult:
    """One Monte Carlo trial of a full unit volley against a unit."""
    target = Target.from_combat_unit(target_unit)
    plan = plan_volley(attacker, phase, target, ctx, rng)
    events: list[DamageEvent] = []
    for die, count in plan:
        for _ in range(count):
            events.extend(resolve_die(die, target, ctx, rng))
    return allocate(events, target, rng)
