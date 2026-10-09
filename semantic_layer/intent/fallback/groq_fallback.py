from __future__ import annotations

import json
import re
from typing import Any

from semantic_layer.intent.models.ast import QueryNode
from semantic_layer.intent.models.enums import (
    INTENT_SCHEMA_VERSION,
    IntentStatus,
    ParserSource,
)
from semantic_layer.intent.models.result import IntentResult
from semantic_layer.intent.validator.ast_validator import AstValidator
from semantic_layer.llm.groq_client import GroqLLMClient
from semantic_layer.normalization.models import NormalizedQuestion

_SYSTEM_PROMPT = """You are the Intent Engine fallback for a semantic NL2SQL pipeline.
Your ONLY job is to produce a validated intent-v1 Abstract Syntax Tree (AST).

You are called ONLY when the deterministic rule engine could not produce a VALID AST
(UNSUPPORTED, AMBIGUOUS, or INVALID). Prefer resolving ambiguity into one best VALID AST
when the question has a clear dominant reading; otherwise keep AMBIGUOUS.

HARD RULES:
- Output a single JSON object. No markdown. No commentary.
- Do NOT invent SQL, table names, column names, joins, or schema.table identifiers.
- Concepts must be canonical semantic names from the provided recognized_concepts when possible.
- Prefer node types: QUERY, RANK, AGGREGATE, BINARY_PREDICATE, BETWEEN_PREDICATE,
  NULL_PREDICATE, TIME_FILTER, COMPARE, CHANGE, RATIO, SUBQUERY, EXISTS,
  DIMENSION_REF, METRIC_REF, ENTITY_REF, LITERAL, LOGICAL, ORDER_BY, CASE.
- Root intent_ast.type must be "QUERY".
- Use JSON key "from" for query sources (not from_).
- If still ambiguous after considering prior rule-engine notes, set status AMBIGUOUS,
  intent_ast null, and list ambiguities.
- If you cannot represent it safely in intent-v1, set status UNSUPPORTED and intent_ast null.

JSON shape:
{
  "schema_version": "intent-v1",
  "status": "VALID" | "AMBIGUOUS" | "UNSUPPORTED",
  "confidence": 0.0-1.0,
  "intent_ast": { "type": "QUERY", ... } | null,
  "ambiguities": [],
  "matched_patterns": ["llm_fallback"]
}
"""


class GroqIntentFallback:
    """LLM IntentFallback via Groq — same intent-v1 contract + AstValidator."""

    def __init__(
        self,
        client: GroqLLMClient | None = None,
        validator: AstValidator | None = None,
    ) -> None:
        self._client = client or GroqLLMClient()
        self._validator = validator or AstValidator()

    def parse(
        self,
        normalized_question: NormalizedQuestion,
        schema_version: str = INTENT_SCHEMA_VERSION,
        *,
        prior: IntentResult | None = None,
    ) -> IntentResult:
        if not self._client.configured:
            return IntentResult(
                schema_version=schema_version,
                status=IntentStatus.UNSUPPORTED,
                confidence=0.0,
                parser=ParserSource.LLM_FALLBACK,
                intent_ast=None,
                errors=["GROQ_API_KEY not configured"],
                ambiguities=list(prior.ambiguities) if prior else [],
            )

        user_prompt = self._build_user_prompt(normalized_question, prior)
        resp = self._client.call_llm(
            prompt=user_prompt,
            system_prompt=_SYSTEM_PROMPT,
            temperature=0.1,
            max_tokens=2048,
            json_object=True,
        )
        try:
            content = GroqLLMClient.extract_content(resp)
            payload = self._parse_json_content(content)
        except Exception as e:  # noqa: BLE001
            return IntentResult(
                schema_version=schema_version,
                status=IntentStatus.UNSUPPORTED,
                confidence=0.0,
                parser=ParserSource.LLM_FALLBACK,
                intent_ast=None,
                errors=[f"LLM fallback parse error: {e}"],
                ambiguities=list(prior.ambiguities) if prior else [],
            )

        return self._to_intent_result(payload, schema_version)

    def _to_intent_result(
        self, payload: dict[str, Any], schema_version: str
    ) -> IntentResult:
        status_raw = str(payload.get("status", "UNSUPPORTED")).upper()
        try:
            status = IntentStatus(status_raw)
        except ValueError:
            status = IntentStatus.UNSUPPORTED

        confidence = float(payload.get("confidence") or 0.0)
        ambiguities = [str(a) for a in (payload.get("ambiguities") or [])]
        matched = [str(p) for p in (payload.get("matched_patterns") or ["llm_fallback"])]
        if "llm_fallback" not in matched:
            matched = ["llm_fallback", *matched]

        ast_raw = payload.get("intent_ast")
        if status == IntentStatus.AMBIGUOUS or ast_raw is None:
            return IntentResult(
                schema_version=schema_version,
                status=status if status != IntentStatus.VALID else IntentStatus.AMBIGUOUS,
                confidence=confidence,
                parser=ParserSource.LLM_FALLBACK,
                intent_ast=None,
                matched_patterns=matched,
                ambiguities=ambiguities or ["LLM reported no AST"],
                errors=[],
            )

        try:
            query = QueryNode.model_validate(ast_raw)
        except Exception as e:  # noqa: BLE001
            return IntentResult(
                schema_version=schema_version,
                status=IntentStatus.INVALID,
                confidence=confidence,
                parser=ParserSource.LLM_FALLBACK,
                intent_ast=None,
                matched_patterns=matched,
                ambiguities=ambiguities,
                errors=[f"LLM AST failed schema parse: {e}"],
            )

        errors = self._validator.validate(query)
        if errors:
            return IntentResult(
                schema_version=schema_version,
                status=IntentStatus.INVALID,
                confidence=confidence,
                parser=ParserSource.LLM_FALLBACK,
                intent_ast=None,
                matched_patterns=matched,
                ambiguities=ambiguities,
                errors=errors,
            )

        return IntentResult(
            schema_version=schema_version,
            status=IntentStatus.VALID,
            confidence=max(confidence, 0.5),
            parser=ParserSource.LLM_FALLBACK,
            intent_ast=query,
            matched_patterns=matched,
            ambiguities=[],
            errors=[],
        )

    @staticmethod
    def _build_user_prompt(
        nq: NormalizedQuestion, prior: IntentResult | None
    ) -> str:
        concepts = [
            {
                "text": c.text,
                "canonical": c.canonical,
                "category": c.category,
            }
            for c in nq.recognized_concepts
        ]
        parts = [
            "Build intent-v1 AST for this normalized question.\n",
            f"original_question: {nq.original_question}",
            f"normalized_question: {nq.normalized_question}",
            f"recognized_concepts: {json.dumps(concepts)}",
            f"unresolved_tokens: {json.dumps(nq.unresolved_tokens)}",
        ]
        if prior is not None:
            parts.extend(
                [
                    "",
                    "Deterministic rule-engine prior (failed to reach VALID):",
                    f"prior_status: {prior.status.value}",
                    f"prior_errors: {json.dumps(prior.errors)}",
                    f"prior_ambiguities: {json.dumps(prior.ambiguities)}",
                    f"prior_matched_patterns: {json.dumps(prior.matched_patterns)}",
                ]
            )
            if prior.status == IntentStatus.AMBIGUOUS:
                parts.append(
                    "Resolve the ambiguity into one VALID intent_ast if a single "
                    "reading clearly dominates; otherwise keep status AMBIGUOUS."
                )
            elif prior.status == IntentStatus.UNSUPPORTED:
                parts.append(
                    "Rules found no safe pattern. Emit a VALID intent_ast if the "
                    "question fits intent-v1; otherwise UNSUPPORTED."
                )
        return "\n".join(parts)

    @staticmethod
    def _parse_json_content(content: str) -> dict[str, Any]:
        text = content.strip()
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            raise ValueError("LLM JSON root must be an object")
        return data
