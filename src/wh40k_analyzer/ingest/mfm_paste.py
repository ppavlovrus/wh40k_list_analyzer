"""L1 adapter: MFM (Munitorum Field Manual) page copy-paste -> points data.

mfm.warhammer-community.com renders points client-side; the practical
extraction path is copy-pasting the rendered page. The paste flattens the
visual cards into a line stream, but the marker vocabulary is small
(``YOUR ... COSTS``, ``LEADER``, ``N models X pts``, ``NDP``), so a state
machine with one-step lookahead recovers the full structure: bracket
pricing (1st-2nd vs 3rd+ copies), leader attach lists, wargear options,
detachments with roles and enhancements, and ▲/▼ deltas vs the previous
MFM release.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

SECTION_HEADERS = {"UNITS", "PLAGUE LEGIONS", "DETACHMENTS"}
DETACH_ROLES = {
    "TAKE AND HOLD",
    "RECONNAISSANCE",
    "PRIORITY ASSETS",
    "DISRUPTION",
    "PURGE THE FOE",
}
TERMINAL_LINES = {"UPDATED", "FORCE DISPOSITION(S) CHANGED"}

COST_MARKER = re.compile(r"^YOUR (.+) COSTS?$")
MODEL_COST = re.compile(r"^(\d+)\s+models?\s*([▲▼])?\s*(?:\(([+-]\d+)\))?\s*(\d+)\s+pts$")
DP_COST = re.compile(r"^(\d+)\s*DP$")
PTS_LINE = re.compile(r"^(\d+)\s+pts$")
WARGEAR_LINE = re.compile(r"^per (.+?)\s*(\d+)\s+pts$")


class MfmCost(BaseModel):
    bracket: str  # e.g. "1ST TO 2ND UNITS COST" / "UNIT"
    models: int
    pts: int
    changed: str | None = None  # ▲ / ▼ vs previous MFM
    delta: int = 0


class MfmUnit(BaseModel):
    name: str
    section: str
    leader_of: list[str] = []  # bodyguard units this model can lead
    costs: list[MfmCost] = []
    wargear: list[dict[str, str | int]] = []
    trend: str | None = None


class MfmEnhancement(BaseModel):
    name: str
    pts: int | None = None


class MfmDetachment(BaseModel):
    name: str
    dp: int
    roles: list[str] = []
    enhancements: list[MfmEnhancement] = []


class MfmDocument(BaseModel):
    units: list[MfmUnit] = []
    detachments: list[MfmDetachment] = []


def parse_mfm_paste(text: str) -> MfmDocument:
    """Parse a copy-pasted MFM faction page into structured points data."""
    units: list[MfmUnit] = []
    detachments: list[MfmDetachment] = []
    section: str | None = None
    current: MfmUnit | None = None
    det: MfmDetachment | None = None
    pending_names: list[str] = []
    pending_bracket: str | None = None
    leader_mode = False
    in_wargear = False
    pending_arrow: str | None = None

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line in TERMINAL_LINES:
            continue
        if line in SECTION_HEADERS:
            section = line  # leader state survives section switches
            continue
        if line == "WARGEAR OPTIONS":
            in_wargear = True
            continue
        if line == "ENHANCEMENTS":
            continue
        if line == "LEADER":
            leader_mode = True
            continue
        if line in ("▲", "▼"):
            pending_arrow = line  # belongs to the next resolved card
            continue

        marker = COST_MARKER.match(line)
        if marker and section != "DETACHMENTS":
            label = marker.group(1).strip()
            if not pending_names:
                pending_bracket = label  # bracket switch inside the same card
                continue
            if leader_mode and current and len(pending_names) >= 2:
                for target_line in pending_names[:-1]:
                    if target_line not in SECTION_HEADERS:
                        current.leader_of.extend(t.strip() for t in target_line.split(","))
            current = MfmUnit(
                name=pending_names[-1],
                section=str(section),
                trend=pending_arrow,
            )
            units.append(current)
            pending_names, leader_mode, in_wargear, pending_arrow = [], False, False, None
            pending_bracket = label
            continue

        m = MODEL_COST.match(line)
        if m and current is not None:
            models, arrow, delta, pts = m.groups()
            current.costs.append(
                MfmCost(
                    bracket=pending_bracket or "UNIT",
                    models=int(models),
                    pts=int(pts),
                    changed=arrow or current.trend or None,
                    delta=int(delta) if delta else 0,
                )
            )
            continue

        if in_wargear and current is not None:
            wm = WARGEAR_LINE.match(line)
            if wm:
                current.wargear.append({"item": wm.group(1), "pts": int(wm.group(2))})
                continue

        dm = DP_COST.match(line)
        if dm and section == "DETACHMENTS":
            name: str | None = None
            if det and det.enhancements and det.enhancements[-1].pts is None:
                # The last "enhancement" without pts was this detachment's name.
                name = det.enhancements.pop().name
            det = MfmDetachment(
                name=name or (pending_names[-1] if pending_names else "?"),
                dp=int(dm.group(1)),
            )
            pending_names = []
            detachments.append(det)
            continue

        if section == "DETACHMENTS" and det is not None:
            if line in DETACH_ROLES:
                det.roles.append(line)
                continue
            if PTS_LINE.match(line):
                det.enhancements[-1].pts = int(line.split()[0])
                continue
            # Enhancement name, or the next detachment's name — decided by
            # whether a pts line or a DP line follows.
            det.enhancements.append(MfmEnhancement(name=line))
            continue

        pending_names.append(line)

    return MfmDocument(units=units, detachments=detachments)
