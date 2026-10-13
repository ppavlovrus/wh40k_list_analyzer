"""Dice mechanics: wound table, rolls, critical detection."""

from __future__ import annotations

import random


def d6(rng: random.Random) -> int:
    return rng.randint(1, 6)


def wound_target(s: int, t: int) -> int:
    """Minimum wound roll needed: the classic S-vs-T ladder."""
    if s >= 2 * t:
        return 2
    if s > t:
        return 3
    if s == t:
        return 4
    if 2 * s > t:
        return 5
    return 6


CRIT = 6  # unmodified 6 on hit or wound rolls


def is_crit(roll: int) -> bool:
    return roll == CRIT


def passes(roll: int, target: int, modifier: int = 0) -> bool:
    """Unmodified 1 always fails, unmodified 6 always succeeds."""
    if roll == 1:
        return False
    if roll == 6:
        return True
    return roll + modifier >= target


def failed_save_target(save: int | None, invuln: int | None, ap: int) -> float:
    """Probability of failing the best available save against AP.

    Armor is worsened by AP (positive ``ap`` here means incoming AP magnitude,
    e.g. 2 for AP-2); invulnerable saves ignore AP. Natural 1 always fails.
    """
    armor = None if save is None else max(save + ap, 2)
    best = min(x for x in (armor, invuln) if x is not None) if (armor or invuln) else None
    if best is None:
        return 1.0
    return (best - 1) / 6
