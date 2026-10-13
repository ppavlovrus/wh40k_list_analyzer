"""L5: human-readable Russian text report of a damage matrix."""

from __future__ import annotations

from wh40k_analyzer.engine.matrix import Cell
from wh40k_analyzer.model.army import Army


def army_header(army: Army) -> str:
    detach = army.detachment.name if army.detachment and army.detachment.name else "—"
    lines = [
        f"{army.name} — {army.faction}",
        f"Очки: {army.points_total}/{army.points_limit or '∞'} · Детачмент: {detach} · "
        f"Боевых юнитов: {len(army.combat_units)}",
        "Юниты:",
    ]
    for unit in army.combat_units:
        attached = f" (+{', '.join(unit.attached_names)})" if unit.attached_names else ""
        lines.append(
            f"  • {unit.name}{attached} — {unit.model_count} мод., "
            f"{unit.wounds_total} W, {unit.points} pts, роль: {unit.role or '—'}"
        )
    return "\n".join(lines)


def matrix_table(cells: list[Cell]) -> str:
    """Attacker rows x defender columns: mean wounds (% HP), P(destroy)."""
    if not cells:
        return "(нет данных)"
    attackers = list(dict.fromkeys(c.attacker for c in cells))
    defenders = list(dict.fromkeys(c.defender for c in cells))
    col_w = max(len(d) for d in defenders) + 2
    header = "Атакующий ↓ / Защитник →".ljust(max(len(a) for a in attackers) + 2)
    header += "".join(d[:18].ljust(col_w) for d in defenders)
    lines = [header, "-" * len(header)]
    by_pair = {(c.attacker, c.defender): c for c in cells}
    for attacker in attackers:
        row = attacker.ljust(max(len(a) for a in attackers) + 2)
        for defender in defenders:
            cell = by_pair.get((attacker, defender))
            if cell is None:
                row += "—".ljust(col_w)
                continue
            pct = round(cell.hp_fraction * 100)
            row += f"{cell.mean_wounds:5.1f}w {pct:3d}%".ljust(col_w)
        lines.append(row)
    lines.append("")
    lines.append("Вероятности уничтожить юнит одним залпом (P=100% если не указано иное):")
    kills = [
        f"  {c.attacker} → {c.defender}: {c.p_destroy:.0%} "
        f"(в среднем {c.mean_slain:.1f} из {c.defender_models} моделей)"
        for c in cells
        if c.p_destroy >= 0.05
    ]
    lines.extend(kills or ["  — ни один залп не убивает юнит целиком с P ≥ 5%"])
    return "\n".join(lines)


def full_report(
    army_a: Army,
    army_b: Army,
    a_vs_b: list[Cell],
    b_vs_a: list[Cell],
    scenario_description: str,
) -> str:
    parts = [
        "=" * 72,
        f"Сценарий: {scenario_description}",
        "",
        army_header(army_a),
        "",
        army_header(army_b),
        "",
        "=" * 72,
        "ЗАЛПЫ АРМИИ A ПО АРМИИ B",
        matrix_table(a_vs_b),
        "",
        "=" * 72,
        "ЗАЛПЫ АРМИИ B ПО АРМИИ A",
        matrix_table(b_vs_a),
        "",
        "=" * 72,
        "Допущения движка: криты — только натуральные 6; overkill теряется; "
        "телохранители гибнут раньше персонажей; Blast даёт кости на оружие "
        "по 1 за каждые 5 моделей цели; рана считается по большинству тела "
        "защитника. Способности юнитов применяются только через сценарий.",
    ]
    return "\n".join(parts)
