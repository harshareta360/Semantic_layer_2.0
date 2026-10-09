from semantic_layer.grounding import GroundingEngine, GroundingStatus
from semantic_layer.ir import IrStatus, compile_query_ir
from semantic_layer.pipeline import Pipeline


def test_ir_finance_rank_revenue():
    full = Pipeline.from_kb(enable_llm_fallback=False).run_full(
        "show top 10 grds by revnue this yr",
        bo_id="Finance",
    )
    cr = full.clauses[0]
    assert cr.grounded is not None
    assert cr.grounded.status == GroundingStatus.VALID
    assert cr.grounded.base_entity == "Payment"
    assert cr.ir is not None
    assert cr.ir.status == IrStatus.VALID
    assert cr.ir.ir is not None
    ir = cr.ir.ir
    assert ir.from_.entity == "Payment"
    assert ir.from_.table == "public_payment_details"
    assert any(s.alias == "total_revenue" for s in ir.select)
    metric = next(s for s in ir.select if s.alias == "total_revenue")
    # Expression must come from grounding/KB — not a compiler hardcode check beyond presence
    assert any(w.source.value == "default_filter" for w in ir.where)
    time_pred = next(w for w in ir.where if w.source.value == "time_filter")
    assert "date_trunc('year', CURRENT_DATE)" in time_pred.sql
    assert "+ interval '1 year'" in time_pred.sql
    assert metric.sql
    assert "SUM" in metric.sql.upper()
    assert ir.limit == 10
    assert cr.ir.sql_preview
    assert "LIMIT 10" in cr.ir.sql_preview.upper()
    # SQLGlot may normalize casts (::numeric → CAST(... AS DECIMAL))
    assert "SUM" in cr.ir.sql_preview.upper()
    assert "amount" in cr.ir.sql_preview.lower()


def test_ir_fails_when_grounding_failed():
    engine = GroundingEngine()
    from semantic_layer.intent.models.result import IntentResult
    from semantic_layer.intent.models.enums import IntentStatus, ParserSource
    from semantic_layer.intent.models.ast import QueryNode, MetricRef

    intent = IntentResult(
        status=IntentStatus.VALID,
        parser=ParserSource.RULE_ENGINE,
        confidence=1.0,
        intent_ast=QueryNode(select=[MetricRef(concept="total_revenue")]),
    )
    grounded = engine.ground(intent, bo_id="Marketing")
    assert grounded.status == GroundingStatus.FAILED
    result = compile_query_ir(intent, grounded)
    assert result.status == IrStatus.FAILED
    assert result.ir is None
