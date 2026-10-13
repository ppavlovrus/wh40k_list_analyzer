# wh40k_list_analyzer

Warhammer 40k (11th edition) army list analyzer. Loads two rosters exported
from New Recruit (Battlescribe-family JSON), resolves attached units, and
computes a mutual damage matrix with situational modifier overlays.

## Architecture (layered)

```
L0 sources:    New Recruit roster JSON | MFM points paste | (future: BSData, wh-rules)
L1 ingest:     roster.py, mfm_paste.py            -> canonical model
L2 canonical:  model/ (Army, CombatUnit, WeaponProfile, StatsLine)
L3 scenario:   overlays.py (curated modifier catalog applied deterministically)
L4 engines:    engine/ (dice, attack resolution, damage matrix)
L5 delivery:   CLI (wh40k) + stdio MCP server
```

New data sources plug in as new L1 modules; canonical model and engines
do not change.

## Usage

```bash
uv sync
wh40k matrix "Salamanders.json" "Death Guard.json" --phase shooting
wh40k mcp          # stdio MCP server for ZCode/Claude integration
```

## Status

MVP in development, see `progress.md`. All Warhammer 40,000 content is
property of Games Workshop; this tool processes user-provided data files.
