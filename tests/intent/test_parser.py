from semantic_layer.intent.fallback import StubIntentFallback
from semantic_layer.intent.models.enums import IntentStatus, ParserSource
from semantic_layer.pipeline import Pipeline


def _pipe() -> Pipeline:
    return Pipeline.from_fixtures()


def test_rank_top_n():
    r = _pipe().run("Show the top 10 grades by revenue.")
    assert r.status == IntentStatus.VALID
    assert r.parser == ParserSource.RULE_ENGINE
    assert "rank_top_n_by_metric" in r.matched_patterns
    assert r.intent_ast is not None
    assert r.intent_ast.limit == 10


def test_rank_with_time():
    r = _pipe().run("show top 10 grds by revnue this yr")
    assert r.status == IntentStatus.VALID
    assert "rank_top_n_by_metric" in r.matched_patterns
    assert "time_filter" in r.matched_patterns


def test_bottom_n():
    r = _pipe().run("Show the bottom 5 grades by revenue.")
    assert r.status == IntentStatus.VALID
    assert "rank_bottom_n_by_metric" in r.matched_patterns


def test_total_revenue():
    r = _pipe().run("What is the total revenue?")
    assert r.status == IntentStatus.VALID
    assert any(p.startswith("aggregate") for p in r.matched_patterns)


def test_total_by_grade():
    r = _pipe().run("What is the total revenue by grade?")
    assert r.status == IntentStatus.VALID
    assert "aggregate_total_by" in r.matched_patterns


def test_average_by_curriculum():
    r = _pipe().run("What is the average revenue by curriculum?")
    assert r.status == IntentStatus.VALID
    assert "aggregate_average_by" in r.matched_patterns


def test_count_learners():
    r = _pipe().run("How many learners registered this year?")
    assert r.status == IntentStatus.VALID
    assert "count_entity" in r.matched_patterns
    assert "time_filter" in r.matched_patterns


def test_threshold_filter():
    r = _pipe().run("Show grades with revenue greater than 5000")
    assert r.status == IntentStatus.VALID
    assert "threshold_greater" in r.matched_patterns


def test_list_entity():
    r = _pipe().run("Show the grades")
    assert r.status == IntentStatus.VALID
    assert "list_show_entity" in r.matched_patterns
    assert r.intent_ast is not None
    assert r.intent_ast.from_


def test_list_with_threshold():
    r = _pipe().run("Show grades with revenue greater than 5000")
    assert r.status == IntentStatus.VALID
    assert "list_show_entity" in r.matched_patterns
    assert "threshold_greater" in r.matched_patterns


def test_list_with_equality_filter():
    r = _pipe().run("Show grades whose status is active")
    assert r.status == IntentStatus.VALID
    assert "list_show_entity" in r.matched_patterns
    assert "equality_is" in r.matched_patterns


def test_order_highest_to_lowest():
    r = _pipe().run("List grades by revenue from highest to lowest")
    assert r.status == IntentStatus.VALID
    assert "list_show_entity" in r.matched_patterns
    assert any(p.startswith("order_") for p in r.matched_patterns)
    assert r.intent_ast is not None
    assert r.intent_ast.order_by


def test_threshold_between():
    r = _pipe().run("Show grades with revenue between 1000 and 5000")
    assert r.status == IntentStatus.VALID
    assert "threshold_between" in r.matched_patterns


def test_rank_not_ambiguous_with_total():
    r = _pipe().run("Show the top 3 grades by total revenue")
    assert r.status == IntentStatus.VALID
    assert "rank_top_n_by_metric" in r.matched_patterns


def test_rank_cheapest():
    r = _pipe().run("What is the cheapest grade by revenue?")
    assert r.status == IntentStatus.VALID
    assert "rank_cheapest" in r.matched_patterns
    assert r.intent_ast is not None
    assert r.intent_ast.limit == 1


def test_rank_which_highest():
    r = _pipe().run("Which grade has the highest revenue?")
    assert r.status == IntentStatus.VALID
    assert "rank_which_highest" in r.matched_patterns
    assert r.intent_ast is not None
    assert r.intent_ast.limit == 1


def test_group_having_more_than():
    r = _pipe().run("Curriculums with more than 100 learners")
    assert r.status == IntentStatus.VALID
    assert "group_having_more_than" in r.matched_patterns
    assert r.intent_ast is not None
    assert r.intent_ast.having is not None


def test_relative_last_n_days():
    r = _pipe().run("Show grades collected in the last 30 days")
    assert r.status == IntentStatus.VALID
    assert "list_show_entity" in r.matched_patterns
    assert "relative_last_n_days" in r.matched_patterns


def test_compare_periods():
    r = _pipe().run("Compare this year's revenue with last year's revenue")
    assert r.status == IntentStatus.VALID
    assert "compare_periods" in r.matched_patterns


def test_yoy_growth():
    r = _pipe().run("Show year over year revenue growth")
    assert r.status == IntentStatus.VALID
    assert "change_yoy" in r.matched_patterns


def test_subquery_threshold():
    r = _pipe().run("Show grades whose revenue is greater than the average revenue")
    assert r.status == IntentStatus.VALID
    assert "subquery_gt_average" in r.matched_patterns


def test_ratio_percentage():
    r = _pipe().run("What percentage of total revenue comes from Grade")
    assert r.status == IntentStatus.VALID
    assert "ratio_percentage" in r.matched_patterns


def test_ambiguous_maximum_by():
    r = _pipe().run("Show the maximum revenue by grade.")
    assert r.status == IntentStatus.AMBIGUOUS
    assert r.intent_ast is None
    assert r.ambiguities


def test_unsupported_window():
    r = _pipe().run("Rank grades using a complex window function over revenue")
    assert r.status == IntentStatus.UNSUPPORTED


def test_stub_fallback_raises():
    from semantic_layer.normalization.models import NormalizedQuestion

    stub = StubIntentFallback()
    try:
        stub.parse(NormalizedQuestion(original_question="x", normalized_question="x"))
        assert False, "expected NotImplementedError"
    except NotImplementedError:
        pass
