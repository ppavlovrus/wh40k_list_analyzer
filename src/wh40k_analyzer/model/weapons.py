"""Weapon profiles of the canonical model."""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel

from wh40k_analyzer.model.stats import DiceExpr, parse_int, parse_range, parse_save, split_keywords

Kind = Literal["ranged", "melee"]

# New Recruit marks alternative weapon modes with this prefix.
MODE_PREFIX = "➤ "

_KEYWORD_PARAM_RE = re.compile(r"^(?P<name>[A-Z][A-Z\- ]+?)\s*(?P<num>\d*\+?)$", re.IGNORECASE)


class WeaponMode(BaseModel):
    """One firing/swing profile of a weapon (e.g. strike vs sweep)."""

    name: str
    kind: Kind
    range_in: int | None = None  # inches; None for melee
    attacks: DiceExpr | None = None  # A
    skill: int | None = None  # BS or WS target roll
    S: int | None = None
    AP: int = 0
    damage: DiceExpr | None = None  # D
    keywords: list[str] = []

    @property
    def is_melee(self) -> bool:
        return self.kind == "melee"

    def keyword_value(self, keyword: str) -> int | None:
        """Extract the numeric parameter of ``keyword`` (e.g. ``Melta 2`` -> 2)."""
        for kw in self.keywords:
            m = _KEYWORD_PARAM_RE.match(kw)
            if m and m.group("name").strip().lower() == keyword.lower():
                num = m.group("num")
                if not num:
                    return None
                return int(num.rstrip("+"))
        return None

    def has_keyword(self, keyword: str) -> bool:
        lowered = keyword.lower()
        for kw in self.keywords:
            m = _KEYWORD_PARAM_RE.match(kw)
            base = m.group("name").strip().lower() if m else kw.lower()
            if base == lowered:
                return True
        return False


class WeaponProfile(BaseModel):
    """A weapon selection with its firing/swing modes."""

    name: str
    kind: Kind
    modes: list[WeaponMode]
    multiplicity: int = 1  # copies per model

    @classmethod
    def from_profiles(
        cls, name: str, kind: Kind, profiles: list[dict[str, Any]], multiplicity: int = 1
    ) -> WeaponProfile:
        modes = []
        for prof in profiles:
            chars = {c["name"]: c.get("$text", "") for c in prof.get("characteristics", [])}
            mode_name = prof.get("name", name).removeprefix(MODE_PREFIX)
            modes.append(
                WeaponMode(
                    name=mode_name,
                    kind=kind,
                    range_in=parse_range(chars.get("Range")) if kind == "ranged" else None,
                    attacks=DiceExpr.parse(chars.get("A")),
                    skill=parse_save(chars.get("BS" if kind == "ranged" else "WS")),
                    S=parse_int(chars.get("S")),
                    AP=parse_int(chars.get("AP")) or 0,
                    damage=DiceExpr.parse(chars.get("D")),
                    keywords=split_keywords(chars.get("Keywords")),
                )
            )
        return cls(name=name, kind=kind, modes=modes, multiplicity=multiplicity)
