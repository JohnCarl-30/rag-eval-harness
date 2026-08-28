from __future__ import annotations

import json

import pytest

from rag_eval_harness.regression.compare import compare_means, load_means_ref
from rag_eval_harness.store.repo import Store


def test_regression_fails_when_mean_drops_past_threshold() -> None:
    report = compare_means(
        {"faithfulness": 0.90, "answer_relevancy": 0.80},
        {"faithfulness": 0.80, "answer_relevancy": 0.79},
        threshold=0.05,
    )
    assert report.passed is False
    failing = {item.metric: item for item in report.failing()}
    assert "faithfulness" in failing
    assert "answer_relevancy" not in failing


def test_regression_passes_within_threshold() -> None:
    report = compare_means({"faithfulness": 0.90}, {"faithfulness": 0.86}, threshold=0.05)
    assert report.passed is True


def test_missing_head_metric_treated_as_zero() -> None:
    report = compare_means({"faithfulness": 0.9}, {}, threshold=0.05)
    assert report.passed is False
    assert report.deltas[0].head == 0.0


def test_load_means_from_file_and_run(store: Store, tmp_path) -> None:
    payload = {"run_id": "file", "means": {"faithfulness": 0.5}}
    path = tmp_path / "base.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    ref, means = load_means_ref(str(path), store)
    assert ref.endswith("base.json")
    assert means["faithfulness"] == 0.5

    from rag_eval_harness.types import EvalRow, MetricSummary, RowScore

    dataset = store.create_dataset([EvalRow(question="Q", answer="A")], name="d")
    run = store.create_run(dataset_id=dataset.id, adapter_type="traces", evaluator="stub")
    store.complete_run(
        run.id,
        MetricSummary(
            means={"faithfulness": 0.42},
            rows=[
                RowScore(
                    question="Q",
                    answer="A",
                    retrieved_contexts=[],
                    ground_truth=None,
                    metrics={"faithfulness": 0.42},
                )
            ],
            error_count=0,
        ),
    )
    _, run_means = load_means_ref(run.id, store)
    assert run_means["faithfulness"] == pytest.approx(0.42)


def test_worst_row_drops_ranks_the_largest_fall() -> None:
    from rag_eval_harness.regression.compare import worst_row_drops
    from rag_eval_harness.types import RowScore

    baseline = [
        RowScore("q0", "a", [], None, {"faithfulness": 0.9}),
        RowScore("q1", "a", [], None, {"faithfulness": 0.8}),
    ]
    head = [
        RowScore("q0", "a", [], None, {"faithfulness": 0.85}),
        RowScore("q1", "a", [], None, {"faithfulness": 0.2}),
    ]
    drops = worst_row_drops(baseline, head, metric="faithfulness", limit=2)
    assert drops[0].index == 1
    assert drops[0].drop == pytest.approx(0.6)
    assert drops[1].index == 0
