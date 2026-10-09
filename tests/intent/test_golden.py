"""Golden regression suite (~100 questions) for Normalization + Intent V1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from semantic_layer.intent.models.enums import IntentStatus
from semantic_layer.pipeline import Pipeline

GOLDEN_PATH = Path(__file__).parent.parent / "fixtures" / "golden_questions.json"
SNAPSHOT_DIR = Path(__file__).parent / "snapshots"


@pytest.fixture(scope="module")
def pipeline() -> Pipeline:
    return Pipeline.from_fixtures()


@pytest.fixture(scope="module")
def golden_cases() -> list[dict]:
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


def test_golden_suite_size(golden_cases):
    assert len(golden_cases) >= 90


def test_all_golden_cases(pipeline: Pipeline, golden_cases: list[dict]):
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    for case_id, case in enumerate(golden_cases):
        result = pipeline.run(case["question"])
        expected_status = IntentStatus(case["expected_status"])
        if result.status != expected_status:
            failures.append(
                f"[{case_id}] {case['question']!r}: expected {expected_status}, "
                f"got {result.status} patterns={result.matched_patterns} "
                f"amb={result.ambiguities} err={result.errors}"
            )
            continue
        for pid in case.get("expected_patterns") or []:
            if pid not in result.matched_patterns:
                failures.append(
                    f"[{case_id}] {case['question']!r}: missing pattern {pid} "
                    f"in {result.matched_patterns}"
                )
        if result.status == IntentStatus.VALID and result.intent_ast is not None:
            payload = result.intent_ast.model_dump(mode="json", by_alias=True)
            snap_path = SNAPSHOT_DIR / f"case_{case_id:03d}_{case.get('id', 'q')}.json"
            text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
            if not snap_path.exists():
                snap_path.write_text(text, encoding="utf-8")
            else:
                existing = snap_path.read_text(encoding="utf-8")
                if existing != text:
                    failures.append(
                        f"[{case_id}] snapshot mismatch for {snap_path.name}"
                    )
    assert not failures, "\n".join(failures[:30])
