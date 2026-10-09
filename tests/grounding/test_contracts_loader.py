from pathlib import Path

from semantic_layer.grounding.contracts import load_grounding_contracts


def test_load_default_overlay():
    contracts = load_grounding_contracts()
    assert contracts is not None
    assert "total_revenue" in contracts.metric_contracts
    assert contracts.resolve_metric_key("revenue") == "total_revenue"
    path = contracts.paths_by_id["cash_revenue_to_grade"]
    assert path.entities[0] == "Payment"
    assert path.entities[-1] == "Grade"


def test_missing_overlay_returns_none(tmp_path: Path):
    assert load_grounding_contracts(tmp_path / "missing.json") is None
