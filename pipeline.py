import sys

from semantic_layer.execute import execute_sql, validate_sql
from semantic_layer.pipeline import Pipeline

# Windows consoles (cp1252) choke on KB arrows / dashes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

pipeline = Pipeline.from_kb()
question = "show top 10 grds by revnue this yr"
bo_id = "Finance"

full = pipeline.run_full(question, bo_id=bo_id)

print("=== NORMALIZATION ===")
print("bo_id:", full.bo_id)
n = full.normalized
print("original_question:", n.original_question)
print("matching_text:", n.matching_text)
print("normalized_question:", n.normalized_question)
print("clauses:", len(n.clauses))
for clause in n.clauses:
    print(f"  [{clause.clause_index}] original:", clause.original_clause)
    print(f"      normalized:", clause.normalized_question)
    print(
        "      concepts:",
        [
            {
                "text": c.text,
                "canonical": c.canonical,
                "category": c.category,
                "confidence": c.confidence,
            }
            for c in clause.recognized_concepts
        ],
    )
    print("      unresolved:", clause.unresolved_tokens)

for i, cr in enumerate(full.clauses):
    print()
    print(f"=== INTENT (clause {i}) ===")
    result = cr.intent
    print("status:", result.status)
    print("parser:", result.parser)
    print("confidence:", result.confidence)
    print("matched_patterns:", result.matched_patterns)
    print("ambiguities:", result.ambiguities)
    print("errors:", result.errors)
    if result.intent_ast is not None:
        print("intent_ast:")
        print(result.intent_ast.model_dump_json(indent=2, by_alias=True))
    else:
        print("intent_ast: null")

    print()
    print("=== GROUNDING (clause {i}) ===".format(i=i))
    g = cr.grounded
    if g is None:
        print("grounded: null")
        continue
    print("bo_id:", g.bo_id)
    print("status:", g.status)
    print("tables:", g.tables)
    print(
        "entities:",
        [
            {
                "concept": e.concept,
                "table": e.source_table,
                "pk": e.primary_key,
                "display_column": e.display_column,
            }
            for e in g.entities
        ],
    )
    print(
        "metrics:",
        [
            {
                "concept": m.concept,
                "sql_expression": m.sql_expression,
                "dependencies": m.dependencies,
                "source": m.source,
            }
            for m in g.metrics
        ],
    )
    print(
        "joins:",
        [
            {
                "from": j.from_entity,
                "to": j.to_entity,
                "on": j.on,
                "join_type": j.join_type,
            }
            for j in g.joins
        ],
    )
    print(
        "time_filters:",
        [t.model_dump() for t in g.time_filters],
    )
    print("unresolved_concepts:", g.unresolved_concepts)
    print("errors:", g.errors)
    print("base_entity:", g.base_entity)
    print("applied_path_ids:", g.applied_path_ids)
    print("default_filters:", g.default_filters)
    print("rules (top):")
    for rule in g.rules[:3]:
        print(" -", rule[:160], "..." if len(rule) > 160 else "")
    print("join_guidance (top):")
    for tip in g.join_guidance[:3]:
        print(" -", tip[:160], "..." if len(tip) > 160 else "")

    print()
    print(f"=== QUERY IR (clause {i}) ===")
    ir = cr.ir
    if ir is None:
        print("ir: null")
        continue
    print("status:", ir.status)
    print("errors:", ir.errors)
    if ir.ir is not None:
        print("query_ir:")
        print(ir.ir.model_dump_json(indent=2, by_alias=True))
    print("sql_preview:")
    print(ir.sql_preview)

    print()
    print(f"=== SQL VALIDATION (clause {i}) ===")
    v = validate_sql(
        ir.sql_preview,
        bo_id=full.bo_id,
        grounded=g,
        ir_result=ir,
    )
    print("status:", v.status)
    print("tables_referenced:", v.tables_referenced)
    print("errors:", v.errors)
    print("warnings:", v.warnings)

    print()
    print(f"=== SQL EXECUTE (clause {i}) ===")
    ex = execute_sql(
        ir.sql_preview or "",
        bo_id=full.bo_id,
        grounded=g,
        ir_result=ir,
    )
    print("status:", ex.status)
    print("row_count:", ex.row_count)
    print("columns:", ex.columns)
    print("error:", ex.error)
    if ex.rows:
        print("rows (up to 5):")
        for row in ex.rows[:5]:
            print(" ", row)

