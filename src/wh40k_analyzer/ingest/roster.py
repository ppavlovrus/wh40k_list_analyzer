"""L1 adapter: New Recruit (Battlescribe-schema) roster JSON -> canonical Army.

The New Recruit export compiles every datasheet profile into the file, so the
roster alone is sufficient: statlines, weapon modes (``➤``-prefixed alternatives),
rule texts, costs, and explicit unit attachments via ``associations``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wh40k_analyzer.model.army import Army, CombatUnit, DetachmentInfo, ModelProfile
from wh40k_analyzer.model.stats import AbilityRef, StatsLine
from wh40k_analyzer.model.weapons import Kind, WeaponProfile

FIELDING_TYPES = {"model", "unit"}
WEAPON_TYPE_NAMES: dict[str, Kind] = {"Ranged Weapons": "ranged", "Melee Weapons": "melee"}
_CHARACTER_CATEGORIES = {"Character", "Epic Hero"}
_GENERIC_DETACHMENT_CATEGORIES = {"Configuration", "Doctrines", "Priority Assets"}


def _sel_costs_pts(sel: dict[str, Any]) -> int:
    return next((int(c["value"]) for c in sel.get("costs", []) if c.get("name") == "pts"), 0)


def _sum_subtree_pts(sel: dict[str, Any]) -> int:
    """Recursive pts sum: squad cost excludes member wargear, so we must descend."""
    total = _sel_costs_pts(sel)
    for child in sel.get("selections", []):
        total += _sum_subtree_pts(child)
    return total


def _categories(sel: dict[str, Any]) -> list[str]:
    return [c.get("name", "") for c in sel.get("categories", [])]


def _primary_category(sel: dict[str, Any]) -> str:
    for c in sel.get("categories", []):
        if c.get("primary"):
            return str(c.get("name", ""))
    return ""


def _profile_chars(prof: dict[str, Any]) -> dict[str, str]:
    return {c["name"]: c.get("$text", "") for c in prof.get("characteristics", [])}


def _abilities(sel: dict[str, Any], owner: str) -> list[AbilityRef]:
    out: dict[str, AbilityRef] = {}
    for prof in sel.get("profiles", []):
        if prof.get("typeName") == "Abilities":
            name = prof.get("name", "")
            out.setdefault(
                name,
                AbilityRef(
                    name=name, description=_profile_chars(prof).get("Description", ""), source=owner
                ),
            )
    for rule in sel.get("rules", []):
        name = rule.get("name", "")
        out.setdefault(
            name, AbilityRef(name=name, description=rule.get("description", ""), source=owner)
        )
    return list(out.values())


def _collect_weapons(sel: dict[str, Any], holder_count: int, out: list[WeaponProfile]) -> None:
    """Collect weapon profiles recursively: wargear may sit in nested
    container selections (e.g. "Thunder Hammer & Storm Shield" wrapping
    the individual weapon entries)."""
    for child in sel.get("selections", []):
        for type_name, kind in WEAPON_TYPE_NAMES.items():
            profs = [p for p in child.get("profiles", []) if p.get("typeName") == type_name]
            if profs:
                number = int(child.get("number", 1) or 1)
                # Weapon number mirrors its holder's model count; per-model copies:
                multiplicity = max(1, number // holder_count) if holder_count else 1
                out.append(
                    WeaponProfile.from_profiles(
                        str(child.get("name", "")), kind, profs, multiplicity
                    )
                )
        _collect_weapons(child, holder_count, out)


def _weapons_of(sel: dict[str, Any], holder_count: int) -> list[WeaponProfile]:
    weapons: list[WeaponProfile] = []
    _collect_weapons(sel, holder_count, weapons)
    return weapons


def _model_profile(sel: dict[str, Any]) -> ModelProfile:
    count = int(sel.get("number", 1) or 1)
    stats = None
    for prof in sel.get("profiles", []):
        if prof.get("typeName") == "Unit":
            stats = StatsLine.from_characteristics(_profile_chars(prof))
            break
    weapons = _weapons_of(sel, count)
    cats = _categories(sel)
    return ModelProfile(
        name=sel.get("name", ""),
        count=count,
        stats=stats,
        weapons=weapons,
        is_character=bool(_CHARACTER_CATEGORIES.intersection(cats)),
    )


def _members_of_unit(sel: dict[str, Any]) -> list[ModelProfile]:
    """Squad members; falls back to the squad's own profile for solo models."""
    members = [
        _model_profile(child) for child in sel.get("selections", []) if child.get("type") == "model"
    ]
    if members:
        return members
    return [_model_profile(sel)]


def _detachment_info(force_sel: list[dict[str, Any]]) -> DetachmentInfo:
    for sel in force_sel:
        if sel.get("name") != "Detachment":
            continue
        children: list[AbilityRef] = []
        name = None
        for child in sel.get("selections", []):
            children.extend(_abilities(child, child.get("name", "")))
            for cat in _categories(child):
                if cat not in _GENERIC_DETACHMENT_CATEGORIES:
                    name = name or cat
        return DetachmentInfo(name=name, children=children)
    return DetachmentInfo()


def load_roster(path: str | Path) -> Army:
    """Load a New Recruit roster export into the canonical model."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    roster = data["roster"]
    # Alliance rosters may carry several forces; merge all of them.
    forces = roster.get("forces", [])

    fielded: list[dict[str, Any]] = [
        s
        for force in forces
        for s in force.get("selections", [])
        if s.get("type") in FIELDING_TYPES and _sel_costs_pts(s) > 0
    ]

    units: dict[str, CombatUnit] = {}
    order: list[str] = []
    for sel in fielded:
        uid = sel["id"]
        unit = CombatUnit(
            uid=uid,
            name=str(sel.get("name", "")),
            role=_primary_category(sel),
            keywords=_categories(sel),
            models=_members_of_unit(sel),
            abilities=_abilities(sel, str(sel.get("name", ""))),
            points=_sum_subtree_pts(sel),
        )
        units[uid] = unit
        order.append(uid)

    # Resolve attachments: outgoing Leading/Supporting merges into the target.
    merged_away: set[str] = set()
    for sel in fielded:
        for assoc in sel.get("associations", []):
            if assoc.get("action") != "group":
                continue
            target = units.get(str(assoc.get("to")))
            leader = units[sel["id"]]
            if target is None or target is leader or sel["id"] in merged_away:
                continue
            for model in leader.models:
                merged = model.model_copy(update={"is_character": True})
                target.models.append(merged)
            seen = {a.name for a in target.abilities}
            target.abilities.extend(a for a in leader.abilities if a.name not in seen)
            target.points += leader.points
            target.attached_names.append(leader.name)
            merged_away.add(sel["id"])

    army_units = [units[uid] for uid in order if uid not in merged_away]

    limit = next(
        (int(c["value"]) for c in roster.get("costLimits", []) if c.get("name") == "pts"), None
    )
    return Army(
        name=str(roster.get("name", Path(path).stem)),
        faction=str(forces[0].get("catalogueName", "")) if forces else "",
        points_total=sum(u.points for u in army_units),
        points_limit=limit,
        detachment=_detachment_info(forces[0].get("selections", []))
        if forces
        else DetachmentInfo(),
        combat_units=army_units,
        source_file=str(path),
    )
