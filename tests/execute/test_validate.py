from semantic_layer.execute import ValidationStatus, validate_sql
from semantic_layer.pipeline import Pipeline


def test_validate_finance_sql_ok():
    full = Pipeline.from_kb(enable_llm_fallback=False).run_full(
        "show top 10 grds by revnue this yr",
        bo_id="Finance",
    )
    cr = full.clauses[0]
    assert cr.ir and cr.ir.sql_preview
    v = validate_sql(
        cr.ir.sql_preview,
        bo_id="Finance",
        grounded=cr.grounded,
        ir_result=cr.ir,
    )
    assert v.status == ValidationStatus.VALID
    assert "public_payment_details" in v.tables_referenced or any(
        "payment" in t for t in v.tables_referenced
    )


def test_validate_rejects_insert():
    v = validate_sql("INSERT INTO public_learners (id) VALUES (1);", bo_id="Finance")
    assert v.status == ValidationStatus.FAILED
    assert v.errors


def test_validate_rejects_foreign_table():
    sql = "SELECT 1 FROM public_logistics_orders LIMIT 1;"
    v = validate_sql(sql, bo_id="Finance")
    assert v.status == ValidationStatus.FAILED
    assert any("allow-list" in e for e in v.errors)
