from __future__ import annotations

from semantic_layer.ir.models import IrSelectKind, QueryIR


def to_sql_postgres(ir: QueryIR) -> str:
    """Thin Postgres SQL preview from QueryIR. Opaque fragments inserted as-is."""
    select_parts: list[str] = []
    for item in ir.select:
        if item.kind == IrSelectKind.COLUMN:
            select_parts.append(
                f'{item.table}."{item.column}" AS {item.alias}'
            )
        else:
            select_parts.append(f"{item.sql} AS {item.alias}")

    lines = [
        "SELECT",
        "  " + ",\n  ".join(select_parts),
        f"FROM {ir.from_.table} AS {ir.from_.alias}",
    ]

    for j in ir.joins:
        jt = (j.join_type or "inner").upper()
        lines.append(f"{jt} JOIN {j.table} AS {j.alias} ON {j.on}")

    if ir.where:
        preds = [w.sql for w in ir.where]
        lines.append("WHERE " + "\n  AND ".join(preds))

    if ir.group_by:
        cols = [f'{g.table}."{g.column}"' for g in ir.group_by]
        lines.append("GROUP BY " + ", ".join(cols))

    if ir.order_by:
        parts = [f"{o.expr_alias} {o.direction}" for o in ir.order_by]
        lines.append("ORDER BY " + ", ".join(parts))

    if ir.limit is not None:
        lines.append(f"LIMIT {int(ir.limit)}")

    return "\n".join(lines) + ";"
