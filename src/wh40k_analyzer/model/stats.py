"""Statlines and dice expressions of the canonical model."""

from __future__ import annotations

import random
import re

from pydantic import BaseModel, Field

_DICE_RE = re.compile(r"^(?:(\d+)\s*)?D(\d+)(?:\s*\+\s*(\d+))?$", re.IGNORECASE)
_MISSING = {"-", "—", "N/A", "*"}
_INT_RE = re.compile(r"^\d+$")


class DiceExpr(BaseModel):
    """A dice expression like ``4``, ``D6``, ``D3+2``.

    ``count`` and ``modifier`` default to 1/0; ``fixed`` expressions have
    ``sides is None`` and carry their value in ``modifier``.
    """

    count: int = 1
    sides: int | None = None
    modifier: int = 0

    @classmethod
    def parse(cls, text: str | int | None) -> DiceExpr | None:
        """Parse a roster characteristic value; ``None`` for ``-``/``N/A``."""
        if text is None:
            return None
        if isinstance(text, int):
            return cls(sides=None, modifier=text)
        s = text.strip()
        if not s or s in _MISSING:
            return None
        if _INT_RE.match(s):
            return cls(sides=None, modifier=int(s))
        m = _DICE_RE.match(s)
        if m:
            count, sides, mod = m.groups()
            return cls(
                count=int(count) if count else 1,
                sides=int(sides),
                modifier=int(mod) if mod else 0,
            )
        msg = f"unparseable dice expression: {s!r}"
        raise ValueError(msg)

    @property
    def expected(self) -> float:
        if self.sides is None:
            return float(self.modifier)
        die = (self.sides + 1) / 2
        return self.count * die + self.modifier

    def roll(self, rng: random.Random) -> int:
        if self.sides is None:
            return self.modifier
        return sum(rng.randint(1, self.sides) for _ in range(self.count)) + self.modifier

    def __str__(self) -> str:
        if self.sides is None:
            return str(self.modifier)
        base = f"{self.count}D{self.sides}" if self.count > 1 else f"D{self.sides}"
        return f"{base}+{self.modifier}" if self.modifier else base


def parse_save(text: str | None) -> int | None:
    """``"3+"`` -> 3 (the minimum roll required); ``None`` for no save."""
    if not text or text.strip() in _MISSING:
        return None
    m = re.match(r"^(\d)\+$", text.strip())
    if not m:
        return None
    return int(m.group(1))


def parse_int(text: str | int | None) -> int | None:
    if text is None:
        return None
    if isinstance(text, int):
        return text
    s = text.strip().strip('"')
    if not s or s in _MISSING:
        return None
    return int(s)


def parse_range(text: str | None) -> int | None:
    """``'12"'`` -> 12 inches; ``Melee``/None -> None."""
    if text is None:
        return None
    s = text.strip().strip('"')
    if not s or not _INT_RE.match(s):
        return None
    return int(s)


class StatsLine(BaseModel):
    """Unit datasheet characteristics."""

    M: str | None = None
    T: int | None = None
    Sv: int | None = None
    W: int | None = None
    Ld: str | None = None
    OC: int | None = None
    invuln: int | None = None
    base: str | None = None

    @classmethod
    def from_characteristics(cls, chars: dict[str, str]) -> StatsLine:
        """Build from a roster profile's ``name -> $text`` map."""
        return cls(
            M=chars.get("M"),
            T=parse_int(chars.get("T")),
            Sv=parse_save(chars.get("Sv")),
            W=parse_int(chars.get("W")),
            Ld=chars.get("LD"),
            OC=parse_int(chars.get("OC")),
            invuln=parse_save(chars.get("InSv")),
            base=chars.get("Base"),
        )


class AbilityRef(BaseModel):
    """Named ability with its rule text (kept verbatim for review)."""

    name: str
    description: str = ""
    source: str = Field(default="", description="selection the ability came from")


def split_keywords(text: str | None) -> list[str]:
    """``"Assault, Blast 1, Torrent"`` -> ``["Assault", "Blast 1", "Torrent"]``."""
    if not text:
        return []
    return [p.strip() for p in text.split(",") if p.strip()]
