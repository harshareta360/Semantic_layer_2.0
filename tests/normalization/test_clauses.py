from semantic_layer.normalization.clause_splitter import split_clauses
from semantic_layer.normalization import NormalizationService
from semantic_layer.normalization.text_cleanup import for_vocab_match, to_matching_text
from semantic_layer.vocabulary import FixtureVocabularyProvider


def test_split_two_questions():
    parts = split_clauses("What is total revenue? Show top 10 grades by revenue")
    assert len(parts) == 2
    assert parts[0].endswith("?")
    assert "top 10" in parts[1].lower()


def test_split_single_question_no_delimiter():
    parts = split_clauses("What is total revenue")
    assert parts == ["What is total revenue"]


def test_matching_text_preserves_question_mark():
    matching = to_matching_text("What is total revenue? Show top 10 grades.")
    assert "?" in matching
    assert matching.startswith("what is")
    vocab = for_vocab_match(matching)
    assert "?" not in vocab


def test_normalize_multi_clause_independently():
    svc = NormalizationService(FixtureVocabularyProvider())
    nq = svc.normalize("What is the total revenue? Show top 10 grades by revenue")
    assert len(nq.clauses) == 2
    assert "?" in nq.matching_text

    c0, c1 = nq.clauses
    assert c0.clause_index == 0
    assert "revenue" in c0.normalized_question
    assert any(c.canonical == "Revenue" for c in c0.recognized_concepts)

    assert c1.clause_index == 1
    assert "grades" in c1.normalized_question
    assert "revenue" in c1.normalized_question
    assert any(c.canonical == "Grade" for c in c1.recognized_concepts)


def test_pipeline_multi_clause_returns_list():
    from semantic_layer.intent.models.enums import IntentStatus
    from semantic_layer.pipeline import Pipeline

    results = Pipeline.from_fixtures().run(
        "What is the total revenue? Show the top 10 grades by revenue."
    )
    assert isinstance(results, list)
    assert len(results) == 2
    assert results[0].status == IntentStatus.VALID
    assert results[1].status == IntentStatus.VALID
    assert any(p.startswith("aggregate") for p in results[0].matched_patterns)
    assert "rank_top_n_by_metric" in results[1].matched_patterns


def test_pipeline_single_clause_still_one_result():
    from semantic_layer.intent.models.result import IntentResult
    from semantic_layer.pipeline import Pipeline

    result = Pipeline.from_fixtures().run("Show the top 10 grades by revenue.")
    assert isinstance(result, IntentResult)
