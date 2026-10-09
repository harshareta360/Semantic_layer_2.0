from __future__ import annotations

import sqlglot
from sqlglot import exp

from semantic_layer.execute.models import ValidationResult, ValidationStatus
from semantic_layer.grounding.business_objects import load_business_objects
from semantic_layer.grounding.models import GroundedContext, GroundingStatus
from semantic_layer.ir.models import IrStatus, QueryIRResult


_FORBIDDEN_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Copy,
    exp.Grant,
    exp.Revoke,
    exp.TruncateTable,
)


def _collect_tables(node: exp.Expression) -> set[str]:
    tables: set[str] = set()
    for t in node.find_all(exp.Table):
        name = t.name
        if t.db:
            name = f"{t.db}.{name}"
        if name:
            tables.add(name)
    return tables


def validate_sql(
    sql: str | None,
    *,
    bo_id: str | None = None,
    grounded: GroundedContext | None = None,
    ir_result: QueryIRResult | None = None,
    dialect: str = "postgres",
) -> ValidationResult:
    """Validate generated SQL before execute (shape + allow-lists)."""
    errors: list[str] = []
    warnings: list[str] = []
    sql_text = (sql or "").strip()

    if ir_result is not None and ir_result.status != IrStatus.VALID:
        errors.append(f"IR status is {ir_result.status}; refuse execute")
    if grounded is not None and grounded.status == GroundingStatus.FAILED:
        errors.append("grounding FAILED; refuse execute")
    if not sql_text:
        errors.append("sql is empty")
        return ValidationResult(
            status=ValidationStatus.FAILED,
            sql=sql_text,
            errors=errors,
        )

    try:
        statements = sqlglot.parse(sql_text, read=dialect)
    except Exception as exc:  # noqa: BLE001
        return ValidationResult(
            status=ValidationStatus.FAILED,
            sql=sql_text,
            errors=[f"SQLGlot parse failed: {exc}"],
        )

    statements = [s for s in statements if s is not None]
    if len(statements) != 1:
        errors.append(f"expected exactly 1 SQL statement, got {len(statements)}")
        return ValidationResult(
            status=ValidationStatus.FAILED,
            sql=sql_text,
            errors=errors,
        )

    tree = statements[0]
    if isinstance(tree, _FORBIDDEN_TYPES) or any(
        tree.find(t) for t in _FORBIDDEN_TYPES
    ):
        errors.append("non-read-only SQL rejected (DDL/DML/admin)")

    # Must be SELECT or WITH ... SELECT
    root = tree
    if isinstance(root, exp.With):
        root = root.this
    if not isinstance(root, exp.Select):
        # Some dialects wrap; also accept Query with select
        if not tree.find(exp.Select):
            errors.append("only SELECT (or WITH … SELECT) is allowed")

    # INTO is write-ish
    if tree.find(exp.Table) and tree.find(exp.Select) and " into " in sql_text.lower():
        # heuristic; also check Select.args
        sel = tree.find(exp.Select)
        if sel is not None and sel.args.get("into") is not None:
            errors.append("SELECT INTO is not allowed")

    tables = sorted(_collect_tables(tree))

    if bo_id:
        reg = load_business_objects()
        if reg is None:
            errors.append("business_objects registry missing; cannot enforce BO allow-list")
        else:
            try:
                bo = reg.require(bo_id)
            except KeyError as exc:
                errors.append(str(exc))
            else:
                allowed = bo.table_names
                # SQL may omit public_ prefix rarely; compare basename too
                allowed_basenames = {t.split(".")[-1] for t in allowed}
                for t in tables:
                    base = t.split(".")[-1]
                    if t not in allowed and base not in allowed_basenames:
                        errors.append(
                            f"table '{t}' not in BO '{bo_id}' allow-list"
                        )

    if grounded is not None:
        allowed_g = set(grounded.tables)
        for e in grounded.entities:
            if e.source_table:
                allowed_g.add(e.source_table)
        if ir_result and ir_result.ir:
            allowed_g.add(ir_result.ir.from_.table)
            for j in ir_result.ir.joins:
                allowed_g.add(j.table)
        for t in tables:
            base = t.split(".")[-1]
            if t not in allowed_g and base not in {x.split(".")[-1] for x in allowed_g}:
                errors.append(f"table '{t}' not in grounded table set")

    status = ValidationStatus.FAILED if errors else ValidationStatus.VALID
    return ValidationResult(
        status=status,
        sql=sql_text,
        tables_referenced=tables,
        errors=errors,
        warnings=warnings,
    )
