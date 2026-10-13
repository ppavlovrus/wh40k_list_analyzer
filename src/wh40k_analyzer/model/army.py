"""Army-level canonical model."""

from __future__ import annotations

from pydantic import BaseModel

from wh40k_analyzer.model.stats import AbilityRef, StatsLine
from wh40k_analyzer.model.weapons import Kind, WeaponProfile


class ModelProfile(BaseModel):
    """A homogeneous group of models inside a combat unit."""

    name: str
    count: int = 1
    stats: StatsLine | None = None
    weapons: list[WeaponProfile] = []
    is_character: bool = False  # leader/support attach or independent character

    @property
    def wounds_total(self) -> int:
        return ((self.stats.W or 0) if self.stats else 0) * self.count


class CombatUnit(BaseModel):
    """A fielded unit with attachments resolved into one combat body."""

    uid: str  # roster instance id (distinguishes duplicates)
    name: str
    role: str = ""  # primary category: Infantry, Vehicle, Character...
    keywords: list[str] = []
    models: list[ModelProfile] = []
    abilities: list[AbilityRef] = []
    points: int = 0
    attached_names: list[str] = []  # leader/support units merged in

    @property
    def wounds_total(self) -> int:
        return sum(m.wounds_total for m in self.models)

    @property
    def model_count(self) -> int:
        return sum(m.count for m in self.models)

    def has_keyword(self, keyword: str) -> bool:
        lowered = keyword.lower()
        return any(
            k.lower() == lowered or k.lower().endswith(f": {lowered}") for k in self.keywords
        )

    def all_weapons(self, kind: Kind | None = None) -> list[tuple[ModelProfile, WeaponProfile]]:
        out = []
        for m in self.models:
            for w in m.weapons:
                if kind is None or w.kind == kind:
                    out.append((m, w))
        return out


class DetachmentInfo(BaseModel):
    """Raw detachment choices captured from the roster."""

    name: str | None = None
    children: list[AbilityRef] = []  # doctrines/assets with rule text


class Army(BaseModel):
    name: str
    faction: str = ""
    points_total: int = 0
    points_limit: int | None = None
    detachment: DetachmentInfo | None = None
    combat_units: list[CombatUnit] = []
    source_file: str = ""

    def unit(self, uid: str) -> CombatUnit | None:
        return next((u for u in self.combat_units if u.uid == uid), None)
