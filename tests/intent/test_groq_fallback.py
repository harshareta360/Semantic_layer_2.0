import json

from semantic_layer.intent.fallback.groq_fallback import GroqIntentFallback
from semantic_layer.intent.models.enums import IntentStatus, ParserSource
from semantic_layer.intent.service import IntentEngine
from semantic_layer.llm.groq_client import GroqLLMClient
from semantic_layer.normalization.models import NormalizedQuestion, RecognizedConcept


class _FakeClient:
    def __init__(self, payload: dict):
        self.payload = payload
        self.configured = True
        self.calls = 0

    def call_llm(self, **kwargs):
        self.calls += 1
        return {
            "choices": [
                {
                    "message": {
                        "content": json.dumps(self.payload),
                    }
                }
            ]
        }


def test_groq_fallback_validates_ast():
    payload = {
        "schema_version": "intent-v1",
        "status": "VALID",
        "confidence": 0.8,
        "intent_ast": {
            "type": "QUERY",
            "select": [
                {
                    "type": "AGGREGATE",
                    "function": "SUM",
                    "argument": {"type": "METRIC_REF", "concept": "total_revenue"},
                }
            ],
            "operations": [],
        },
        "matched_patterns": ["llm_fallback"],
        "ambiguities": [],
    }
    fb = GroqIntentFallback(client=_FakeClient(payload))  # type: ignore[arg-type]
    nq = NormalizedQuestion(
        original_question="weird phrasing for total revenue",
        matching_text="weird phrasing for total revenue",
        normalized_question="weird phrasing for total revenue",
        recognized_concepts=[
            RecognizedConcept(
                text="revenue", canonical="total_revenue", category="MEASURE"
            )
        ],
    )
    result = fb.parse(nq)
    assert result.status == IntentStatus.VALID
    assert result.parser == ParserSource.LLM_FALLBACK
    assert result.intent_ast is not None


def test_engine_uses_fallback_only_when_rules_fail():
    payload = {
        "status": "VALID",
        "confidence": 0.7,
        "intent_ast": {
            "type": "QUERY",
            "select": [{"type": "METRIC_REF", "concept": "total_revenue"}],
        },
    }
    fake = _FakeClient(payload)
    engine = IntentEngine(
        fallback=GroqIntentFallback(client=fake),  # type: ignore[arg-type]
        use_llm_fallback=True,
    )
    # No recognizable pattern → rules UNSUPPORTED → LLM
    nq = NormalizedQuestion(
        original_question="please illuminate fiscal yield",
        matching_text="please illuminate fiscal yield",
        normalized_question="please illuminate fiscal yield",
        recognized_concepts=[
            RecognizedConcept(
                text="revenue", canonical="total_revenue", category="MEASURE"
            )
        ],
    )
    result = engine.parse(nq)
    assert fake.calls == 1
    assert result.parser == ParserSource.LLM_FALLBACK

    # Clear ranking pattern → rules VALID → no LLM
    fake.calls = 0
    nq2 = NormalizedQuestion(
        original_question="show top 10 grades by revenue",
        matching_text="show top 10 grades by revenue",
        normalized_question="show top 10 grades by revenue",
        recognized_concepts=[
            RecognizedConcept(text="grades", canonical="Grade", category="ENTITY"),
            RecognizedConcept(
                text="revenue", canonical="total_revenue", category="MEASURE"
            ),
        ],
    )
    result2 = engine.parse(nq2)
    assert fake.calls == 0
    assert result2.parser == ParserSource.RULE_ENGINE
    assert result2.status == IntentStatus.VALID


def test_engine_escalates_ambiguous_to_llm():
    """Rule AMBIGUOUS (e.g. maximum … by) should call LLM with prior context."""
    payload = {
        "status": "VALID",
        "confidence": 0.75,
        "intent_ast": {
            "type": "QUERY",
            "select": [
                {
                    "type": "AGGREGATE",
                    "function": "MAX",
                    "argument": {"type": "METRIC_REF", "concept": "total_revenue"},
                }
            ],
            "group_by": [{"type": "DIMENSION_REF", "concept": "Grade"}],
        },
    }
    fake = _FakeClient(payload)
    engine = IntentEngine(
        fallback=GroqIntentFallback(client=fake),  # type: ignore[arg-type]
        use_llm_fallback=True,
    )
    nq = NormalizedQuestion(
        original_question="Show the maximum revenue by grade.",
        matching_text="Show the maximum revenue by grade.",
        normalized_question="show the maximum revenue by grade",
        recognized_concepts=[
            RecognizedConcept(text="grade", canonical="Grade", category="ENTITY"),
            RecognizedConcept(
                text="revenue", canonical="total_revenue", category="MEASURE"
            ),
        ],
    )
    result = engine.parse(nq)
    assert fake.calls == 1
    assert result.parser == ParserSource.LLM_FALLBACK
    assert result.status == IntentStatus.VALID


def test_groq_client_reads_model_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "test-key")
    monkeypatch.setenv("MODEL", "openai/gpt-oss-120b")
    client = GroqLLMClient()
    assert client.model == "openai/gpt-oss-120b"
    assert client.configured
