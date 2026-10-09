# Hybrid Low-LLM NL2SQL Architecture

Block-wise component design

## 1. Overall Pipeline

```
┌─────────────────────────────────────────────────────────────┐
│ USER QUESTION                                               │
│ Original natural-language question                          │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ 1. NORMALIZATION                                            │
│ Rules + NLP + LLM fallback                                  │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ NORMALIZED QUESTION                                         │
│ Canonical question + extracted concepts                     │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ 2. INTENT ENGINE                                            │
│ Intent grammar / classifier + LLM fallback                  │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ INTENT AST                                                   │
│ Composable query operations (semantic, not SQL)             │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ 3. KB GROUNDING                                             │
│ BM25 + Vector + Rules + Reranker                            │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ GROUNDED CONTEXT                                            │
│ Resolved business concepts, schema, relationships and rules │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ 4. QUERY IR                                                 │
│ Deterministic IR construction + validation                  │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ QUERY IR                                                    │
│ Structured representation of the query                      │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ 5. SQL BUILDER                                              │
│ SQLGlot AST                                                 │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ SQL                                                         │
│ Deterministic SQL                                           │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ 6. SQL VALIDATOR                                            │
│ Parser + schema + safety validation                         │
└─────────────────────────────────────────────────────────────┘
↓
┌─────────────────────────────────────────────────────────────┐
│ EXECUTE / RETRY                                             │
│ Execute, classify failures, repair or escalate              │
└─────────────────────────────────────────────────────────────┘
```

## 2. Component 1 — Normalization

Purpose: convert the user's raw question into a clean, canonical form while preserving all meaningful information.

One-line rule: **Normalization = "What the user said — cleaned and canonicalized."**

### Input

Example:

```
"show me top 10 grds having max revnue in this yr"
```

### What Normalization does

**A. Basic text normalization**

- casing
- whitespace
- punctuation
- basic linguistic cleanup

**B. Typo correction**

```
grds   → grades
revnue → revenue
```

**C. Domain terminology recognition**

Use a thin vocabulary built from the existing KB Entity and Measure names plus their synonyms. Do not write manual per-typo rules such as "search for grds".

```
grds   → Grade
revnue → Revenue
```

### How much of the KB is used?

Thin layer of KB only:

```
Entity
 ├── canonical name
 └── synonyms

Measure
 ├── canonical name
 └── synonyms
```

Normalization generally does **not** use relationships, DB mappings, business rules, examples, or detailed descriptions. Those belong in Grounding.

### Which words are searched in the KB?

No manually defined word-list. Build a **Vocabulary Index** from the KB:

```
grade    → Grade
grd      → Grade
grds     → Grade

revenue  → Revenue
rev      → Revenue
revnue   → Revenue
```

Match question tokens/phrases against this vocabulary. Do not force unknown/general words into KB search.

### What about top, max, count, this year?

These are **not** domain KB concepts. They are **query / intent vocabulary**.

Normalization:

```
top 10  → preserve
max     → preserve
this yr → this year
```

Intent (later):

```
top 10    → ranking + limit 10
max       → highest / descending
this year → time filter
```

Normalization itself does **not** decide SQL meaning.

### Most important rule

Normalization must not lose information.

For example, `"max revenue"` must not be reduced to just `"revenue"`. Keep `max`, because the Intent layer later decides what it means in context.

### Normalization vs Intent vs Grounding

```
USER QUESTION
      ↓
┌─────────────────────┐
│   NORMALIZATION     │
│                     │
│ • Text cleanup      │
│ • Typo correction   │
│ • KB vocabulary     │
│ • Entity recognition│
│ • Measure recognition│
│ • Preserve meaning  │
└─────────────────────┘
      ↓
NORMALIZED QUESTION
      ↓
┌─────────────────────┐
│    INTENT ENGINE    │
│                     │
│ top / max / count   │
│ ranking / filter    │
│ aggregation / etc.  │
└─────────────────────┘
      ↓
      GROUNDING
      ↓
   QUERY IR
      ↓
   SQLGlot
      ↓
      SQL
```

Remember:

- **Normalization** = "What the user said — cleaned and canonicalized."
- **Intent** = "What the user actually wants to do — converted into query operations."
- **Grounding** = "What those concepts mean in this database — resolved from the KB."

## 3. Component 2 — Intent Engine

### Purpose

The Intent Layer converts the **Normalized Question** into a structured **Intent AST (Abstract Syntax Tree)** that represents what the user wants to achieve from the data.

The Intent Layer focuses on **query intent and operations**, not on database-specific implementation. It does not decide which tables, columns, joins, or SQL syntax should be used.

### Flow

```text
User Question
      ↓
Normalization
      ↓
Normalized Question
      ↓
Intent Engine
      ↓
Intent AST
      ↓
Grounding
      ↓
Query IR
      ↓
SQLGlot
      ↓
SQL
```

### Intent AST

The Intent AST acts as a structured semantic representation of the user's request.

Instead of producing a flat JSON with a fixed set of parameters, the Intent AST should be **generic, composable, and recursive** so that it can represent simple as well as complex analytical queries.

Typical AST node types may include:

```text
QUERY
FILTER
AGGREGATE
GROUP_BY
SORT
RANK
COMPARE
SUBQUERY
TREND
DISTINCT
TOP_N
```

The schema and allowed node types are predefined, while the actual values are derived dynamically from the normalized question and recognized concepts.

### Example 1 — Aggregation

Question:

> "What is the total revenue by grade?"

Intent AST:

```text
AGGREGATE
├── function: SUM
├── metric: Revenue
└── group_by: Grade
```

### Example 2 — Ranking

Question:

> "Show the top 10 grades by revenue this year."

Intent AST:

```text
RANK
├── dimension: Grade
├── metric: Revenue
├── direction: DESC
├── limit: 10
└── filter
      └── time: THIS_YEAR
```

### Example 3 — Comparison

Question:

> "Compare this year's revenue with last year's revenue."

Intent AST:

```text
COMPARE
├── left
│   └── METRIC
│       ├── metric: Revenue
│       └── period: THIS_YEAR
│
└── right
    └── METRIC
        ├── metric: Revenue
        └── period: LAST_YEAR
```

### Example 4 — Subquery

Question:

> "Show grades whose revenue is greater than the average revenue."

Intent AST:

```text
FILTER
├── left
│   └── METRIC
│       └── Revenue
├── operator: >
└── right
    └── SUBQUERY
        └── AGGREGATE
            ├── function: AVG
            └── metric: Revenue
```

Because the AST is recursive, a subquery can itself contain another operation or query structure.

### Example 5 — Complex Query

Question:

> "Show the top 5 grades whose revenue is above the average revenue, along with their year-over-year growth."

Conceptually:

```text
QUERY
├── RANK
│   ├── dimension: Grade
│   ├── metric: Revenue
│   ├── direction: DESC
│   └── limit: 5
│
├── FILTER
│   └── Revenue
│       >
│       SUBQUERY
│       └── AVG(Revenue)
│
└── COMPARE
    ├── Revenue
    ├── THIS_YEAR
    └── LAST_YEAR
```

This demonstrates that multiple operations such as **ranking, filtering, subqueries, and comparisons** can be composed within a single Intent AST.

### Predefined vs Dynamic Information

The Intent AST schema defines the **structure and allowed operations**, such as:

```text
Node Types:
RANK
FILTER
AGGREGATE
COMPARE
SUBQUERY
SORT
TREND

Aggregations:
SUM
AVG
COUNT
MIN
MAX

Operators:
=
>
<
>=
<=
IN
BETWEEN

Directions:
ASC
DESC
```

The actual values are identified dynamically from the normalized question, such as:

```text
Grade
Revenue
Curriculum
Learner
Payment
10
5000
THIS_YEAR
LAST_YEAR
```

### Boundary with Grounding

The Intent Layer identifies **what the user wants**, but it does not determine how those concepts are implemented in the database.

For example:

```text
Intent:
    dimension = Grade
    metric = Revenue
    operation = RANK
```

The Grounding Layer then determines:

```text
Grade
    → actual entity/table/column mapping

Revenue
    → actual measure definition and database mapping

THIS_YEAR
    → applicable date column and business rule
```

### Key Principle

**Intent = What does the user want?**

**Grounding = What do those concepts mean in this database?**

**Query IR = How should that request be structurally executed?**

**SQLGlot = How should that structure be expressed as SQL?**

The Intent AST therefore acts as the **semantic bridge between natural language and executable query construction**, while remaining independent of database-specific SQL implementation.

## 4. Component 3 — KB Grounding

Purpose: resolve the concepts from the Intent AST against the existing Knowledge Base.

- Schema KB
- Semantic KB
- Example KB
- Relationship information
- Business knowledge
- Metric definitions
- Column mappings
- Synonyms
- Rules / Guardrails

Recommended retrieval:

Intent AST + NormalizedQuestion → BM25 + Vector Retrieval → Rules → Reranking → GroundedContext

Example:

```
revenue → Metric Definition → SUM(public_academic_bag.net_price)

grade → Semantic Mapping → public_grades_master.name

grade ↔ revenue → Relationship KB → valid JOIN path
```

## 5. Component 4 — Query IR Generator

Purpose: convert grounded information into a structured intermediate representation. SQL is not generated at this stage.

Conceptual structure:

```
QueryIR(
  source=...,
  joins=[...],
  filters=[...],
  dimensions=[...],
  measures=[...],
  group_by=[...],
  order_by=[...],
  limit=10
)
```

IR validation:

- Table and column existence
- Valid JOIN paths
- Aggregation validity
- GROUP BY consistency
- Metric validity
- Filter datatype compatibility
- Business-rule compliance

## 6. Component 5 — SQL Builder

Purpose: deterministically convert the validated QueryIR into SQL using SQLGlot.

QueryIR → SQLGlot AST → SQL

No LLM is required for SQL construction.

- No table hallucination
- No column hallucination
- No prompt-based SQL generation
- Controlled SQL dialect
- Reproducible output

## 7. Component 6 — SQL Validator

Purpose: validate the generated SQL before execution.

- SQL parsing
- Schema validation
- Safety validation
- Business-rule validation
- Execution validation

If execution fails: classify the error deterministically → repair IR when possible → regenerate SQL. Use an LLM only when the failure requires unresolved semantic reasoning.

## 8. Conditional LLM Usage

The LLM is a fallback reasoning component, not the brain of the complete system.

- Normal Path: Question → Normalizer → Intent → KB → IR → SQLGlot → SQL
- Ambiguous Language: Normalizer → uncertainty → LLM → normalized representation
- Low-Confidence Grounding: KB retrieval → low confidence → LLM semantic resolver → GroundedContext
- Execution Failure: SQL → DB error → deterministic repair → LLM only if unresolved

## 9. Confidence-Based Control

| Confidence | Action | Goal |
| --- | --- | --- |
| ≥ 0.90 | Continue | High-confidence result |
| 0.70–0.90 | Retrieve / rerank | Resolve uncertainty without immediate LLM use |
| < 0.70 | LLM fallback / clarification | Use reasoning when deterministic methods are insufficient |

## 10. Why This Architecture?

- Minimum practical dependency on LLMs
- Knowledge Base remains the semantic source of truth
- Deterministic and reproducible SQL generation
- Clear separation of language understanding, grounding and SQL construction
- Lower risk of hallucinated schema objects
- Independent testing of every pipeline stage
- Better debugging and observability
- Easier benchmarking across a large question set

## 11. End-to-End Example

| Component | Result |
| --- | --- |
| User | What are the top 10 grades by revenue this year? |
| Normalization | Canonical question + concepts: grade, revenue, this year |
| Intent | RANK AST: Grade × Revenue, DESC, limit 10, THIS_YEAR filter |
| Grounding | Resolve metric, dimension, date semantics and JOIN path from KB |
| IR | Build source, joins, filters, measures, grouping and ordering |
| SQL Builder | Convert QueryIR into SQLGlot AST and SQL |
| Validation | Parse, schema-check, safety-check and execute |

## 12. Final Architecture

```
USER
  ↓
NORMALIZATION
  ↓
INTENT
  ↓
SEMANTIC KB + SCHEMA KB + RELATIONSHIPS + BUSINESS RULES
  ↓
QUERY IR
  ↓
SQLGLOT
  ↓
SQL VALIDATION
  ↓
DATABASE
```

## 13. Detailed Walkthrough — One Question Through Every Component

The following example shows how one natural-language question moves through the complete pipeline. The example is intentionally simple enough to explain the architecture, while demonstrating the separation between language understanding, KB grounding, IR construction, and deterministic SQL generation.

### Example Question

"What are the top 10 grades by revenue this year?"

### Step 1 — User Question

Input:

"What are the top 10 grades by revenue this year?"

At this point the system has only the user's natural-language request. It does not yet assume which tables, columns, metrics, or JOINs are required.

### Step 2 — Normalization

The normalizer converts the raw question into a clean, canonical form while preserving all meaningful information. It uses basic text cleanup, typo correction, and a thin KB vocabulary index (Entity/Measure names + synonyms) for domain terminology. It does not assign SQL meaning to query words such as top, max, or this year, and it must not drop tokens like max.

Input → Raw user question

"show me top 10 grds having max revnue in this yr"

Output:

```json
{
  "original_question": "show me top 10 grds having max revnue in this yr",

  "normalized_question":
    "Show me the top 10 grades having max revenue this year.",

  "concepts": [
    {
      "original": "top 10",
      "canonical": "top 10"
    },
    {
      "original": "grds",
      "canonical": "Grade"
    },
    {
      "original": "max",
      "canonical": "max"
    },
    {
      "original": "revnue",
      "canonical": "Revenue"
    },
    {
      "original": "this yr",
      "canonical": "this year"
    }
  ]
}
```

### Step 3 — Intent Engine

The Intent Engine converts the Normalized Question into a structured **Intent AST**. It answers: 'What operations does the user want?' It does not answer: 'Which database objects should I use?' Query/intent vocabulary such as top, max, and this year is interpreted here as operations (for example RANK + limit, DESC, time filter). The AST is composable and recursive; it is not a flat fixed-parameter JSON.

Output (Intent AST):

```text
RANK
├── dimension: Grade
├── metric: Revenue
├── direction: DESC
├── limit: 10
└── filter
      └── time: THIS_YEAR
```

The Intent AST describes the semantic shape of the request. It intentionally contains no physical table or column names — those are resolved later by Grounding.

### Step 4 — KB Grounding

Now the system uses the Intent AST plus the normalized question to retrieve and resolve information from the KB.

The grounding process can look like:

```
Intent AST + NormalizedQuestion
        ↓
BM25 retrieval + Vector retrieval
        ↓
Rules / mappings
        ↓
Reranking
        ↓
GroundedContext
```

Example resolutions:

1. 'revenue' → Metric Definition → SUM(public_academic_bag.net_price)

2. 'grade' → Semantic Mapping → public_grades_master.name

3. grade ↔ revenue → Relationship KB → valid JOIN path

4. 'this year' → Date/business rule → appropriate date predicate and source column

The important point is that the KB, not the LLM, determines how the business concept 'revenue' is implemented in this database.

### Step 5 — Grounded Context

After grounding, the system has enough information to build a query.

Conceptual output:

```json
{
  "metric": {
    "name": "revenue",
    "expression": "SUM(public_academic_bag.net_price)"
  },
  "dimension": {
    "name": "grade",
    "column": "public_grades_master.name"
  },
  "relationships": ["valid grade-to-revenue JOIN path"],
  "filters": ["this_year date predicate"]
}
```

This is the point where business meaning has been grounded into database meaning.

### Step 6 — Query IR Generation

The IR Generator takes the grounded context and constructs a structured query plan. This is still not raw SQL.

Conceptual QueryIR:

```
SELECT
  dimension = public_grades_master.name
  measure = SUM(public_academic_bag.net_price)

FROM
  grounded source table

JOIN
  grounded valid relationship

WHERE
  grounded this-year predicate

GROUP BY
  public_grades_master.name

ORDER BY
  SUM(public_academic_bag.net_price) DESC

LIMIT
  10
```

The IR validator can now check whether every table/column exists, the JOIN path is valid, aggregation and GROUP BY are consistent, filters are compatible, and business rules are satisfied.

### Step 7 — SQL Builder with SQLGlot

Only after the IR passes validation do we build SQL. SQLGlot converts the IR into a SQL AST and renders the target SQL dialect.

Flow:

QueryIR → SQLGlot AST → SQL

The resulting SQL will conceptually look like:

```sql
SELECT
    public_grades_master.name AS grade,
    SUM(public_academic_bag.net_price) AS revenue
FROM ...
JOIN ... ON ...
WHERE ...
GROUP BY public_grades_master.name
ORDER BY revenue DESC
LIMIT 10;
```

The exact FROM, JOIN, and WHERE clauses come from the grounded KB information and QueryIR; they are not invented by an LLM.

### Step 8 — SQL Validation and Execution

Before execution:

- Parse the generated SQL.
- Validate referenced schema objects.
- Check safety constraints.
- Check applicable business rules.
- Execute the query.

If execution fails, first classify the error deterministically. If the issue can be fixed by changing the IR or applying a known rule, repair the IR and regenerate SQL. If the issue is genuinely semantic and cannot be resolved deterministically, invoke the LLM as a fallback.

### Step 9 — Final Result

The database returns the top 10 grades and their revenue values. A downstream response/visualization layer can then present the result to the user.

### Complete Example Flow

```
User Question
     ↓
Normalization
     ↓
NormalizedQuestion
     ↓
Intent Engine
     ↓
Intent AST
     ↓
KB Grounding
     ↓
GroundedContext
     ↓
Query IR + Validation
     ↓
SQLGlot
     ↓
SQL + Validation
     ↓
Database
     ↓
Final Answer
```

### Key Takeaway

The LLM does not need to generate SQL. It is used only where language interpretation or semantic ambiguity cannot be handled confidently by deterministic logic and the KB. The KB supplies the business and database knowledge, QueryIR provides the control layer, and SQLGlot provides deterministic SQL construction.


## 17. IR Generation — Detailed Design

IR (Intermediate Representation) generation is the deterministic bridge between the user's intent and SQL. It should not depend on an LLM. The IR Generator receives two structured inputs: the Intent AST and the Grounded Context.

```
Intent AST  +  Grounded Context
↓
IR Generator
↓
QueryIR
```

### 17.1 What the Intent AST Represents

The Intent AST describes what the user wants without containing database-specific implementation details.

Example question: “What are the top 10 grades by revenue this year?”

Intent AST:

```text
RANK
├── dimension: Grade
├── metric: Revenue
├── direction: DESC
├── limit: 10
└── filter
      └── time: THIS_YEAR
```

### 17.2 What Grounding Provides

The Grounding stage resolves the business concepts in the Intent AST against the Knowledge Base.

Example:

```
revenue
    → SUM(public_academic_bag.net_price)

grade
    → public_grades_master.name

relationship
    → academic_bag → enrollment → grade

this_year
    → appropriate date predicate
```

### 17.3 IR Generator

The IR Generator combines the Intent AST and Grounded Context using deterministic mapping rules. It translates intent operations into executable query structures.

```
Intent AST + Grounded Context
        ↓
    IR Builder
        ↓
┌──────────────────────────┐
│ QueryIR                  │
│                          │
│ FROM                     │
│ JOIN                     │
│ SELECT                   │
│ FILTER                   │
│ GROUP BY                 │
│ ORDER BY                 │
│ LIMIT                    │
└──────────────────────────┘
```

### 17.4 Example QueryIR

```json
{
  "from": "public_academic_bag",

  "joins": [
    {
      "table": "public_learner_enrollment",
      "on": "..."
    },
    {
      "table": "public_grades_master",
      "on": "..."
    }
  ],

  "select": [
    {
      "expression": "public_grades_master.name",
      "alias": "grade"
    },
    {
      "expression": "SUM(public_academic_bag.net_price)",
      "alias": "revenue"
    }
  ],

  "filters": [
    {
      "expression": "...",
      "operator": "...",
      "value": "..."
    }
  ],

  "group_by": [
    "public_grades_master.name"
  ],

  "order_by": [
    {
      "expression": "revenue",
      "direction": "DESC"
    }
  ],

  "limit": 10
}
```

### 17.5 Why IR Should Be Deterministic

- The Intent AST already describes the required operations.
- Grounding has already resolved the concepts into database-specific information.
- The IR Generator only needs to combine these two structured inputs.
- Deterministic construction makes the query plan reproducible and easier to test.
- The IR can be validated before any SQL is generated.
- An LLM is therefore unnecessary for normal IR creation.

### 17.6 IR Validation Before SQL

Before passing QueryIR to SQLGlot, validate:

- Every referenced table exists.
- Every referenced column exists.
- The selected metric is valid.
- JOIN paths are valid according to the KB.
- Aggregations are compatible with GROUP BY.
- Filters are compatible with column datatypes.
- ORDER BY expressions are valid.
- LIMIT/OFFSET values are valid.
- Business rules and guardrails are satisfied.

### 17.7 Final Separation of Responsibilities

| Stage | Question it answers | Example |
| --- | --- | --- |
| Intent | What does the user want? | Rank grades by revenue |
| Grounding | What do those concepts mean in this database? | revenue → SUM(net_price) |
| IR | How should the grounded request be structurally executed? | GROUP BY grade, ORDER BY revenue DESC, LIMIT 10 |
| SQLGlot | How do we express that structure as SQL? | Generate SQL AST and render SQL |

### 17.8 Overall Flow

```
NORMALIZED QUESTION
        ↓
   INTENT PARSER
        ↓
    Intent AST
        ↓
  KB GROUNDING
        ↓
Grounded Intent AST
        ↓
   IR GENERATOR
        ↓
      QueryIR
        ↓
   IR VALIDATOR
        ↓
     SQLGLOT
        ↓
       SQL
```
