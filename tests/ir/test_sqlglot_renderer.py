from semantic_layer.ir import render_sql
from semantic_layer.pipeline import Pipeline


def test_sqlglot_renders_finance_rank_sql():
    full = Pipeline.from_kb(enable_llm_fallback=False).run_full(
        "show top 10 grds by revnue this yr",
        bo_id="Finance",
    )
    cr = full.clauses[0]
    assert cr.ir is not None and cr.ir.ir is not None
    sql = cr.ir.sql_preview or ""
    assert "SELECT" in sql.upper()
    assert "public_payment_details" in sql
    assert "public_grades_master" in sql
    assert "SUM" in sql.upper()
    assert "payment_status" in sql
    assert "date_trunc" in sql.lower()
    assert "LIMIT" in sql.upper()
    # Ensure primary path used SQLGlot (no fallback warning for happy path)
    assert not any("sqlglot render failed" in e for e in cr.ir.errors)

    # Explicit render API
    again = render_sql(cr.ir.ir, dialect="postgres")
    assert "SELECT" in again.upper()
    assert again.strip().endswith(";")
