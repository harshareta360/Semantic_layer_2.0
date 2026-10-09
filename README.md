# Semantic Layer 2.0 — Normalization + Intent + Grounding V1

Deterministic pipeline:

```text
User Question → Normalization → Intent → Grounding → Query IR (+ SQL preview)
```

**Full step-by-step flow with input/output examples:** see [`docs/FLOW.md`](docs/FLOW.md).  
**Known V1 limits:** see [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md).

## Setup

```bash
python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS/Linux
# source venv/bin/activate

pip install -e ".[dev]"
```

## Run tests

```bash
.\venv\Scripts\pytest
```

## Quick start

```python
from semantic_layer.pipeline import Pipeline

# Uses kb.json + grounding_contracts.json + Groq Intent fallback when rules miss
pipeline = Pipeline.from_kb()
full = pipeline.run_full("show top 10 grds by revnue this yr", bo_id="Finance")
cr = full.clauses[0]
print(cr.intent.status, cr.intent.matched_patterns)
print(cr.grounded.bo_id, cr.grounded.status, cr.grounded.applied_path_ids, cr.grounded.tables)
print(cr.ir.status if cr.ir else None)
print(cr.ir.sql_preview if cr.ir else None)
```

Intent-only (backward compatible): `pipeline.run(...)` → `IntentResult` (or list for multi-clause).

Disable LLM: `Pipeline.from_kb(enable_llm_fallback=False)`.

For isolated unit tests with a tiny vocab, use `Pipeline.from_fixtures()` (LLM off by default).

Demo: `python pipeline.py` prints Normalization + Intent + Grounding.

**Readable UI:** `python demo_ui.py` then open http://127.0.0.1:8765 — enter question + BO, then **Validate SQL** / **Execute SQL** (needs `PG_*` in `.env`).

## Docs

| Doc | Contents |
|-----|----------|
| [`docs/FLOW.md`](docs/FLOW.md) | Normalization + Intent + Grounding steps, I/O examples |
| [`docs/LIMITATIONS.md`](docs/LIMITATIONS.md) | Known V1 limitations |
| [`docs/NORMALIZATION_ROADMAP.md`](docs/NORMALIZATION_ROADMAP.md) | Normalization improvement roadmap |
| [`docs/superpowers/specs/2026-09-21-normalization-intent-v1-design.md`](docs/superpowers/specs/2026-09-21-normalization-intent-v1-design.md) | Locked V1 design |
| [`docs/intent_ast_implementation_plan.md`](docs/intent_ast_implementation_plan.md) | Original Intent AST plan |
