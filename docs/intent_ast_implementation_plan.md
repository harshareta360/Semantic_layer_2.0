# Intent AST Implementation Plan

## 1. Objective

Implement a deterministic-first **Intent Engine** that converts the output of the existing Normalization layer into a validated **Intent AST (Abstract Syntax Tree)**.

The Intent Engine must:

- Accept a normalized natural-language question.
- Recognize query intent and intent-bearing operators.
- Use canonical concepts already identified by Normalization.
- Build a recursive, composable Intent AST.
- Validate the AST against a fixed schema.
- Return a versioned, structured Intent result.
- Remain independent of physical database tables, columns, joins, and SQL syntax.
- Be designed so that an optional LLM fallback can be added later without changing the AST contract.
- Not generate SQL.
- Not perform database-specific grounding.

### Target flow

```text
User Question
     ↓
Normalization Layer
     ↓
Normalized Question
     ↓
Intent Engine
     ├── Pattern / Rule Parser
     ├── Concept Extraction
     ├── AST Builder
     └── AST Validator
     ↓
Validated Intent AST
     ↓
Grounding Layer
     ↓
Query IR
     ↓
SQLGlot
     ↓
SQL
```

---

# 2. Important Architectural Boundaries

## Normalization owns

- Basic text normalization.
- Spelling/typo correction.
- Abbreviation normalization.
- Recognition/canonicalization of KB vocabulary.
- Preservation of semantic information.

Example:

```text
"show top 10 grds by revnue this yr"

→

"show top 10 grades by revenue this year"
```

Normalization may attach recognized concepts:

```text
grds   → Grade
revnue → Revenue
this yr → THIS_YEAR
```

## Intent owns

- Determining the requested analytical operation.
- Interpreting query operators such as:
  - top / bottom
  - highest / lowest
  - average / total / count
  - greater than / less than
  - compare / versus
  - trend / growth / change
  - percentage / share
  - between / in / not in
- Building the semantic query structure.
- Combining operations recursively.

## Grounding owns

- Physical table mapping.
- Physical column mapping.
- Metric definitions.
- Relationship/JOIN resolution.
- Business rules.
- Database-specific date logic.
- KB knowledge beyond vocabulary/concept recognition.

## Query IR owns

- Executable query planning.
- Physical query structure.
- Join plan.
- Select structure.
- Grouping.
- Filters.
- Ordering.
- CTE/subquery execution structure.

## SQLGlot owns

- SQL AST generation.
- SQL dialect output.
- SQL rendering.

---

# 3. Implementation Principles

1. **Do not hardcode database table/column names into the Intent Engine.**
2. **Do not generate SQL in the Intent Engine.**
3. **Do not use a flat list of special-case parameters for every possible query.**
4. Use a **recursive AST**.
5. Prefer deterministic rules and patterns before any LLM fallback.
6. Preserve ambiguity rather than silently guessing.
7. Validate every generated AST.
8. Version the schema from the beginning.
9. Keep the AST database-independent.
10. Make each transformation testable independently.

---

# 4. Recommended Project Structure

Inspect the existing project first and adapt names to the current repository structure. Do not duplicate existing utilities.

Recommended logical structure:

```text
intent/
├── __init__.py
├── models/
│   ├── __init__.py
│   ├── ast.py
│   ├── enums.py
│   └── result.py
│
├── parser/
│   ├── __init__.py
│   ├── intent_parser.py
│   ├── pattern_matcher.py
│   ├── operator_parser.py
│   ├── expression_parser.py
│   └── temporal_parser.py
│
├── builder/
│   ├── __init__.py
│   └── ast_builder.py
│
├── validator/
│   ├── __init__.py
│   └── ast_validator.py
│
├── vocabulary/
│   ├── __init__.py
│   └── intent_vocabulary.py
│
├── confidence/
│   ├── __init__.py
│   └── confidence.py
│
├── fallback/
│   ├── __init__.py
│   └── llm_fallback.py
│
└── service.py

tests/
├── intent/
│   ├── test_ast_models.py
│   ├── test_parser.py
│   ├── test_ranking.py
│   ├── test_aggregation.py
│   ├── test_filters.py
│   ├── test_comparison.py
│   ├── test_subquery.py
│   ├── test_trend.py
│   ├── test_nested_intents.py
│   ├── test_validator.py
│   └── test_end_to_end.py
```

If an equivalent module already exists, extend it rather than creating a competing implementation.

---

# 5. Phase 0 — Repository Discovery

Before writing implementation code, inspect the repository.

### Find

1. Existing normalization implementation.
2. Existing KB access layer.
3. Existing synonyms/entity/measure loading.
4. Existing pipeline/orchestrator.
5. Existing shared Pydantic/data models.
6. Existing LLM client.
7. Existing schema utilities.
8. Existing temporal/date parsing utilities.
9. Existing tests.
10. Existing logging/error handling patterns.

### Output of this phase

Create a short internal implementation note:

```text
Existing normalization entry point:
<path>

Existing KB vocabulary provider:
<path>

Existing pipeline entry point:
<path>

Existing shared models:
<path>

Existing LLM client:
<path>

Existing tests:
<path>
```

Do not duplicate functionality already present.

---

# 6. Phase 1 — Define the Intent AST Contract

Use typed Python models.

Prefer **Pydantic models** if Pydantic is already used in the project.

Create:

```text
intent/models/enums.py
intent/models/ast.py
intent/models/result.py
```

## 6.1 Schema version

Every output must contain:

```json
{
  "schema_version": "intent-v1"
}
```

Use a constant:

```python
INTENT_SCHEMA_VERSION = "intent-v1"
```

---

# 7. Core AST Node Model

Use a discriminated `type` field.

Base concept:

```python
class ASTNode(BaseModel):
    type: str
```

Prefer explicit subclasses and a discriminated union over an untyped dictionary.

---

# 8. Required Node Types

Implement at least:

```text
QUERY

ENTITY_REF
DIMENSION_REF
METRIC_REF
LITERAL
PARAMETER

AGGREGATE

FILTER
LOGICAL
BINARY_PREDICATE
IN_PREDICATE
BETWEEN_PREDICATE
NULL_PREDICATE

GROUP_BY
ORDER_BY

RANK
COMPARE
CHANGE
RATIO

TIME_FILTER

SUBQUERY
EXISTS

CASE

WINDOW

SET_OPERATION
```

Do not implement SQL-specific nodes unless required by the semantic contract.

---

# 9. Reference Nodes

## Entity

```json
{
  "type": "ENTITY_REF",
  "concept": "Learner"
}
```

## Dimension

```json
{
  "type": "DIMENSION_REF",
  "concept": "Grade"
}
```

## Metric

```json
{
  "type": "METRIC_REF",
  "concept": "Revenue"
}
```

Important:

The `concept` must be a canonical semantic concept.

Do not store:

```text
public_academic_bag.net_price
public_grades_master.name
```

inside Intent AST.

Those mappings belong to Grounding.

---

# 10. Literal Node

```json
{
  "type": "LITERAL",
  "value": 5000,
  "data_type": "NUMBER"
}
```

Supported data types:

```text
STRING
NUMBER
BOOLEAN
DATE
DATETIME
TIME
NULL
```

---

# 11. Aggregate Node

Supported functions:

```text
SUM
AVG
COUNT
COUNT_DISTINCT
MIN
MAX
```

Example:

```json
{
  "type": "AGGREGATE",
  "function": "SUM",
  "argument": {
    "type": "METRIC_REF",
    "concept": "Revenue"
  }
}
```

---

# 12. Predicate Model

Operators:

```text
=
!=
>
<
>=
<=
LIKE
IN
NOT_IN
BETWEEN
IS_NULL
IS_NOT_NULL
```

Example:

```json
{
  "type": "BINARY_PREDICATE",
  "operator": ">",
  "left": {
    "type": "METRIC_REF",
    "concept": "Revenue"
  },
  "right": {
    "type": "LITERAL",
    "value": 5000,
    "data_type": "NUMBER"
  }
}
```

---

# 13. Logical Node

Support:

```text
AND
OR
NOT
```

Example:

```json
{
  "type": "LOGICAL",
  "operator": "AND",
  "conditions": [
    {...},
    {...}
  ]
}
```

This must be recursively composable.

---

# 14. Time Filter

Do not resolve physical date columns in Intent.

Support:

```text
TODAY
YESTERDAY
THIS_WEEK
LAST_WEEK
THIS_MONTH
LAST_MONTH
THIS_QUARTER
LAST_QUARTER
THIS_YEAR
LAST_YEAR
DATE_RANGE
RELATIVE_DATE_RANGE
```

Example:

```json
{
  "type": "TIME_FILTER",
  "range": "THIS_YEAR"
}
```

---

# 15. Ordering

```json
{
  "type": "ORDER_BY",
  "expression": {
    "type": "METRIC_REF",
    "concept": "Revenue"
  },
  "direction": "DESC"
}
```

Allowed:

```text
ASC
DESC
```

---

# 16. Ranking

Ranking is an explicit semantic operation.

Example:

> Show top 10 grades by revenue.

```json
{
  "type": "RANK",
  "dimension": {
    "type": "DIMENSION_REF",
    "concept": "Grade"
  },
  "metric": {
    "type": "METRIC_REF",
    "concept": "Revenue"
  },
  "direction": "DESC",
  "limit": 10
}
```

---

# 17. Comparison

Example:

> Compare this year's revenue with last year's revenue.

```json
{
  "type": "COMPARE",
  "left": {
    "type": "METRIC_EXPRESSION",
    "metric": "Revenue",
    "period": "THIS_YEAR"
  },
  "right": {
    "type": "METRIC_EXPRESSION",
    "metric": "Revenue",
    "period": "LAST_YEAR"
  },
  "comparison_type": "PERIOD_OVER_PERIOD"
}
```

Support at least:

```text
PERIOD_OVER_PERIOD
GROUP_TO_GROUP
METRIC_TO_METRIC
VALUE_TO_VALUE
```

---

# 18. Change / Growth

Example:

> Show year-over-year revenue growth.

```json
{
  "type": "CHANGE",
  "metric": {
    "type": "METRIC_REF",
    "concept": "Revenue"
  },
  "current_period": "THIS_YEAR",
  "previous_period": "LAST_YEAR",
  "change_type": "PERCENT_CHANGE"
}
```

Support:

```text
ABSOLUTE_CHANGE
PERCENT_CHANGE
GROWTH_RATE
```

---

# 19. Ratio / Percentage

Example:

> What percentage of total revenue comes from Grade 10?

Use:

```json
{
  "type": "RATIO",
  "numerator": {...},
  "denominator": {...},
  "output": "PERCENTAGE"
}
```

The numerator and denominator must be expressions, allowing recursive composition.

---

# 20. Subquery

The AST must be recursive.

Example:

> Show grades whose revenue is greater than the average revenue.

```json
{
  "type": "BINARY_PREDICATE",
  "operator": ">",
  "left": {
    "type": "METRIC_REF",
    "concept": "Revenue"
  },
  "right": {
    "type": "SUBQUERY",
    "query": {
      "type": "QUERY",
      "select": [
        {
          "type": "AGGREGATE",
          "function": "AVG",
          "argument": {
            "type": "METRIC_REF",
            "concept": "Revenue"
          }
        }
      ]
    }
  }
}
```

Subqueries must be allowed anywhere the schema permits an expression.

---

# 21. Query Node

Define:

```python
class QueryNode(BaseModel):
    type: Literal["QUERY"] = "QUERY"
    select: list[ExpressionNode] = []
    from_: list[SourceNode] = []
    where: PredicateNode | None = None
    group_by: list[ExpressionNode] = []
    having: PredicateNode | None = None
    order_by: list[OrderByNode] = []
    limit: int | None = None
    offset: int | None = None
    distinct: bool = False
    set_operation: SetOperationNode | None = None
```

Use `from_` in Python if `from` conflicts with Python syntax, but serialize as `"from"`.

---

# 22. Final Intent Result Envelope

The Intent Engine must return:

```json
{
  "schema_version": "intent-v1",
  "status": "VALID",
  "confidence": 0.96,
  "parser": "RULE_ENGINE",
  "intent_ast": {...}
}
```

Allowed status:

```text
VALID
AMBIGUOUS
UNSUPPORTED
INVALID
```

Allowed parser source:

```text
RULE_ENGINE
CLASSIFIER
LLM_FALLBACK
```

The AST itself remains the same regardless of parser source.

---

# 23. Phase 2 — Intent Vocabulary

Create a small **query intent vocabulary**, separate from the KB domain vocabulary.

Do NOT duplicate the KB entity/measure vocabulary.

The intent vocabulary should contain operators and linguistic patterns.

## Operation vocabulary

```text
RANK
AGGREGATE
FILTER
GROUP
SORT
COMPARE
TREND
CHANGE
RATIO
DISTINCT
SUBQUERY
EXISTS
WINDOW
SET_OPERATION
```

## Aggregation vocabulary

```text
SUM
AVG
COUNT
COUNT_DISTINCT
MIN
MAX
```

## Comparison vocabulary

```text
GREATER_THAN
LESS_THAN
EQUAL
NOT_EQUAL
GREATER_OR_EQUAL
LESS_OR_EQUAL
```

## Ranking vocabulary

```text
TOP
BOTTOM
HIGHEST
LOWEST
MAXIMUM
MINIMUM
```

Important semantic rule:

`MAXIMUM` must not automatically become `MAX()`.

Example:

> "Top 10 grades by maximum revenue"

may indicate ranking by highest revenue.

Whereas:

> "What is the maximum revenue?"

indicates the `MAX` aggregation.

Context must determine the AST representation.

---

# 24. Phase 3 — Pattern/Grammar Layer

Build a pattern matcher.

The matcher must detect intent structures rather than only single keywords.

Examples:

## Ranking pattern

```text
TOP <N> <DIMENSION> BY <METRIC>
```

Maps to:

```text
RANK
```

## Aggregate pattern

```text
TOTAL <METRIC> BY <DIMENSION>
```

Maps to:

```text
AGGREGATE(SUM) + GROUP_BY
```

## Average pattern

```text
AVERAGE <METRIC> BY <DIMENSION>
```

Maps to:

```text
AGGREGATE(AVG) + GROUP_BY
```

## Comparison pattern

```text
<PERIOD_1> VS <PERIOD_2>
```

Maps to:

```text
COMPARE
```

## Threshold pattern

```text
<EXPRESSION> GREATER THAN <VALUE>
```

Maps to:

```text
BINARY_PREDICATE
```

## Subquery pattern

```text
<EXPRESSION> GREATER THAN THE AVERAGE OF <EXPRESSION>
```

Maps to:

```text
BINARY_PREDICATE
    right = SUBQUERY
```

Patterns should be data-driven where practical instead of scattering strings across Python files.

---

# 25. Phase 4 — Concept Integration

The Intent Engine receives concepts recognized by Normalization.

Example normalized representation:

```json
{
  "normalized_question": "Show the top 10 grades by revenue this year.",
  "recognized_concepts": [
    {
      "text": "grades",
      "canonical": "Grade",
      "category": "ENTITY"
    },
    {
      "text": "revenue",
      "canonical": "Revenue",
      "category": "MEASURE"
    },
    {
      "text": "this year",
      "canonical": "THIS_YEAR",
      "category": "TIME"
    }
  ]
}
```

The Intent Engine should consume these canonical concepts instead of re-solving the same vocabulary problem.

---

# 26. Phase 5 — AST Construction

Create:

```text
intent/builder/ast_builder.py
```

Responsibilities:

1. Accept parsed intent signals.
2. Construct typed AST nodes.
3. Compose nodes recursively.
4. Never resolve DB tables/columns.
5. Never generate SQL.

Example:

```python
AstBuilder().build(parsed_intent)
```

---

# 27. Phase 6 — AST Validation

Every AST must pass structural validation before leaving the Intent Engine.

Validate:

### Structural

- Required fields exist.
- Node type is supported.
- Child node types are valid.
- Recursive structure is valid.

### Semantic

- `RANK` has dimension + metric.
- `RANK.limit` is positive integer.
- `AGGREGATE` has valid function.
- `COMPARE` has valid operands.
- `BETWEEN` has two boundaries.
- `IN` has a list/subquery.
- `SUBQUERY` contains a valid `QUERY`.
- `ORDER_BY` has valid direction.
- `GROUP_BY` contains expressions.
- No invalid nesting.

### Database independence

Reject physical DB identifiers:

```text
public_*
column_name
schema.table
SQL fragment
JOIN condition
```

from the Intent AST.

---

# 28. Phase 7 — Confidence

Each parser decision should carry confidence internally.

Suggested policy:

```text
>= 0.90
    → accept AST

0.70 - 0.90
    → perform additional deterministic parsing/validation

< 0.70
    → ambiguity handling / optional LLM fallback
```

These thresholds should be configurable, not hardcoded throughout the codebase.

Confidence should be compositional where possible.

Example:

```text
RANK detection = 0.98
Grade concept = 0.99
Revenue concept = 0.99
Time filter = 0.97

Overall AST confidence ≈ confidence policy
```

Do not claim mathematical probability unless the scoring system is calibrated.

---

# 29. Phase 8 — Ambiguity Handling

Never silently force an ambiguous interpretation.

Example:

> "Show the maximum revenue by grade."

Potential ambiguity:

1. MAX aggregation.
2. Ranking/highest revenue.

If parser confidence is insufficient:

```json
{
  "status": "AMBIGUOUS",
  "confidence": 0.58,
  "intent_ast": null,
  "ambiguities": [
    {
      "term": "maximum",
      "possible_interpretations": [
        "MAX aggregation",
        "ranking by highest revenue"
      ]
    }
  ]
}
```

Do not send a guessed AST downstream.

---

# 30. Phase 9 — Optional LLM Fallback

Do not make LLM the default.

Pipeline:

```text
Rules / Grammar
      ↓
AST
      ↓
Validation
      ↓
Confident?
  ├── YES → return
  └── NO
       ↓
Classifier / semantic parser
       ↓
Still unresolved?
  ├── YES → optional LLM fallback
  └── NO → return
```

If an LLM fallback is implemented:

- Give it the normalized question.
- Give it the exact Intent AST schema.
- Give it allowed node types.
- Give it allowed operators/functions.
- Require structured output.
- Validate output using the same AST validator.
- Never allow arbitrary SQL.
- Never allow physical DB mappings.

The LLM must generate the same `intent-v1` contract.

---

# 31. Phase 10 — Parser API

Expose a simple service interface.

Example:

```python
class IntentEngine:
    def parse(
        self,
        normalized_question: NormalizedQuestion
    ) -> IntentResult:
        ...
```

Expected:

```python
result = intent_engine.parse(normalized_question)
```

Output:

```python
IntentResult(
    schema_version="intent-v1",
    status="VALID",
    confidence=0.96,
    parser="RULE_ENGINE",
    intent_ast=query_ast,
)
```

---

# 32. Phase 11 — Pipeline Integration

Find the existing pipeline/orchestrator.

Add:

```text
Normalization
      ↓
Intent Engine
      ↓
Grounding
```

Do not merge Intent and Grounding.

The Grounding interface should consume only a validated Intent AST and normalized question/context.

Example:

```python
grounded_context = grounding_engine.ground(
    intent_result.intent_ast,
    normalized_question
)
```

---

# 33. Phase 12 — Examples That Must Work

Implement tests for at least these:

### Basic aggregation

```text
What is the total revenue?
```

Expected:

```text
AGGREGATE(SUM, Revenue)
```

### Grouped aggregation

```text
What is the total revenue by grade?
```

Expected:

```text
AGGREGATE(SUM, Revenue)
GROUP_BY(Grade)
```

### Average

```text
What is the average revenue by curriculum?
```

Expected:

```text
AGGREGATE(AVG, Revenue)
GROUP_BY(Curriculum)
```

### Count

```text
How many learners registered this year?
```

Expected:

```text
COUNT(Learner)
TIME_FILTER(THIS_YEAR)
```

### Ranking

```text
Show the top 10 grades by revenue.
```

Expected:

```text
RANK(Grade, Revenue, DESC, 10)
```

### Bottom-N

```text
Show the bottom 5 grades by revenue.
```

Expected:

```text
RANK(Grade, Revenue, ASC, 5)
```

### Filter

```text
Show grades where revenue is greater than 50000.
```

Expected:

```text
FILTER(Revenue > 50000)
```

### Compound filter

```text
Show grades where revenue is greater than 50000 and enrollment is above 1000.
```

Expected:

```text
AND(
    Revenue > 50000,
    Enrollment > 1000
)
```

### Comparison

```text
Compare revenue this year versus last year.
```

Expected:

```text
COMPARE(
    Revenue@THIS_YEAR,
    Revenue@LAST_YEAR
)
```

### YoY

```text
Show year-over-year revenue growth.
```

Expected:

```text
CHANGE(
    Revenue,
    THIS_YEAR,
    LAST_YEAR,
    PERCENT_CHANGE
)
```

### Percentage

```text
What percentage of total revenue comes from grade 10?
```

Expected:

```text
RATIO(
    revenue_for_grade_10,
    total_revenue
)
```

### Subquery

```text
Show grades whose revenue is greater than average revenue.
```

Expected:

```text
FILTER(
    Revenue >
    SUBQUERY(
        AVG(Revenue)
    )
)
```

### Distinct

```text
Show distinct curricula.
```

Expected:

```text
DISTINCT(Curriculum)
```

### Exists

```text
Show learners who have made a payment.
```

Expected:

```text
EXISTS(Payment)
```

### Nested query

```text
Show the top 5 grades whose revenue is above average revenue.
```

Expected:

```text
RANK(
    FILTER(
        Revenue >
        SUBQUERY(AVG(Revenue))
    ),
    Grade,
    Revenue,
    DESC,
    5
)
```

The exact internal tree can differ, but the semantics must be preserved.

---

# 34. Negative / Ambiguity Tests

Add tests where the parser must NOT guess.

Examples:

```text
Show maximum revenue by grade.
```

Potential ambiguity:

```text
MAX aggregation
vs
highest/ranking interpretation
```

Expected:

```text
AMBIGUOUS
```

unless an explicit grammar rule resolves it consistently.

Also test:

```text
Show revenue.
```

If `revenue` is recognized as a metric but no aggregation/output behavior is implied, the system must follow the project-defined default semantics or return ambiguity. Do not invent behavior silently.

---

# 35. AST Snapshot Testing

For every supported intent pattern:

1. Parse normalized question.
2. Serialize AST deterministically.
3. Compare against expected JSON fixture.

Directory:

```text
tests/intent/fixtures/
```

Example:

```text
ranking_top10_revenue_grade.json
comparison_yoy_revenue.json
subquery_avg_revenue.json
percentage_revenue_grade.json
```

This prevents accidental schema drift.

---

# 36. Validation Test

Every generated AST should satisfy:

```python
validate_intent_ast(ast) == True
```

Also test invalid ASTs manually.

Examples:

```text
RANK without metric
AGGREGATE without argument
invalid aggregation
negative LIMIT
invalid operator
malformed SUBQUERY
physical table names
SQL fragments
```

These must fail validation.

---

# 37. Observability

Log:

```text
request_id
normalized_question
parser_used
recognized_patterns
recognized_concepts
AST
confidence
validation_status
fallback_used
```

Do not log sensitive user data unnecessarily.

The AST should be serializable for debugging.

---

# 38. No-SQL Rule

Add a hard architectural rule:

```text
Intent layer MUST NOT:
- generate SQL
- import SQLGlot
- access database schema mappings
- construct JOINs
- choose physical tables
- choose physical columns
```

Intent should only produce semantic structure.

---

# 39. No-KB-Deep-Dive Rule

The Intent Engine may receive canonical concepts from Normalization and may use lightweight intent vocabulary.

It should NOT resolve:

```text
Grade
    → actual table/column

Revenue
    → actual formula

Payment
    → actual join path
```

Those belong to Grounding.

---

# 40. Definition of Done

The Intent Engine implementation is complete when:

- [ ] `intent-v1` schema exists.
- [ ] Typed AST models exist.
- [ ] AST node types are implemented.
- [ ] Recursive expressions are supported.
- [ ] Ranking is supported.
- [ ] Aggregation is supported.
- [ ] Filtering is supported.
- [ ] Grouping is supported.
- [ ] Sorting is supported.
- [ ] Comparison is supported.
- [ ] Trend/change is supported.
- [ ] Ratio/percentage is supported.
- [ ] Subqueries are supported.
- [ ] EXISTS is supported.
- [ ] DISTINCT is supported.
- [ ] Compound logical conditions are supported.
- [ ] AST validation exists.
- [ ] Ambiguity handling exists.
- [ ] Confidence exists.
- [ ] Parser source is recorded.
- [ ] Intent Engine integrates after Normalization.
- [ ] No SQL generation exists in Intent.
- [ ] No physical DB mapping exists in Intent.
- [ ] Snapshot tests exist.
- [ ] Positive and negative tests exist.
- [ ] Existing pipeline behavior is not broken.

---

# 41. Implementation Order

Implement strictly in this order:

```text
1. Inspect existing repository
        ↓
2. Define intent-v1 models/enums
        ↓
3. Implement AST validation
        ↓
4. Implement reference/concept handling
        ↓
5. Implement basic intent grammar
        ↓
6. Implement AST builder
        ↓
7. Implement ranking/aggregation/filter/group/sort
        ↓
8. Implement comparison/change/time
        ↓
9. Implement recursive subqueries
        ↓
10. Implement ratio/distinct/exists
        ↓
11. Implement ambiguity + confidence
        ↓
12. Integrate with existing pipeline
        ↓
13. Add snapshot + regression tests
        ↓
14. Add optional LLM fallback only after deterministic
            implementation is stable
```

---

# 42. Important Instruction for Cursor

Before modifying code:

1. Inspect the current repository.
2. Identify existing normalization, KB, pipeline, models, and tests.
3. Reuse existing infrastructure.
4. Do not create duplicate KB loaders or synonym systems.
5. Do not modify the existing SQL generation path yet.
6. Implement the Intent Engine behind a clean interface.
7. Keep changes modular and reversible.
8. Add tests with every major AST feature.
9. Run the existing test suite after integration.
10. Do not claim support for a query pattern unless a test demonstrates it.

The first implementation milestone should be:

```text
Normalized Question
        ↓
Deterministic Intent Parser
        ↓
intent-v1 AST
        ↓
AST Validator
```

Only after this works reliably should the implementation proceed to deeper intent types and optional fallback mechanisms.
