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


def test_more_errored_rows_fails_even_with_equal_means() -> None:
    means = {"faithfulness": 0.8}
    report = compare_means(means, means, baseline_errors=0, head_errors=15)
    assert report.errors_increased is True
    assert report.passed is False
    assert report.failing() == []


def test_error_check_skipped_when_counts_unknown_or_not_worse() -> None:
    means = {"faithfulness": 0.8}
    assert compare_means(means, means, baseline_errors=3, head_errors=3).passed is True
    assert compare_means(means, means, baseline_errors=3, head_errors=1).passed is True
    assert compare_means(means, means, baseline_errors=None, head_errors=9).passed is True


def test_load_errors_ref_from_snapshot_rows_and_means_only(tmp_path) -> None:
    from rag_eval_harness.regression.compare import load_errors_ref

    counted = tmp_path / "counted.json"
    counted.write_text(json.dumps({"means": {}, "error_count": 4}), encoding="utf-8")
    assert load_errors_ref(str(counted)) == 4
    rows = tmp_path / "rows.json"
    rows.write_text(json.dumps({"means": {}, "rows": [{"error": "x"}, {}]}), encoding="utf-8")
    assert load_errors_ref(str(rows)) == 1
    bare = tmp_path / "bare.json"
    bare.write_text(json.dumps({"means": {"faithfulness": 0.5}}), encoding="utf-8")
    assert load_errors_ref(str(bare)) is None


def test_row_drops_pair_by_question_not_position() -> None:
    from rag_eval_harness.regression.compare import pair_rows, worst_row_drops
    from rag_eval_harness.types import RowScore

    baseline = [
        RowScore("q0", "a", [], None, {"faithfulness": 0.9}),
        RowScore("q1", "a", [], None, {"faithfulness": 0.2}),
        RowScore("gone", "a", [], None, {"faithfulness": 0.9}),
    ]
    # Reordered, one row removed, one added: nothing actually got worse.
    head = [
        RowScore("new", "a", [], None, {"faithfulness": 0.1}),
        RowScore("q1", "a", [], None, {"faithfulness": 0.2}),
        RowScore("q0", "a", [], None, {"faithfulness": 0.9}),
    ]
    assert worst_row_drops(baseline, head) == []
    pairs = pair_rows(baseline, head)
    assert [(b and b.question, h and h.question) for b, h in pairs] == [
        (None, "new"),
        ("q1", "q1"),
        ("q0", "q0"),
        ("gone", None),
    ]


def test_pair_rows_matches_repeated_questions_in_order() -> None:
    from rag_eval_harness.regression.compare import pair_rows
    from rag_eval_harness.types import RowScore

    baseline = [RowScore("q", "first", [], None, {}), RowScore("q", "second", [], None, {})]
    head = [RowScore("q", "x", [], None, {}), RowScore("q", "y", [], None, {})]
    assert [b.answer for b, _ in pair_rows(baseline, head)] == ["first", "second"]
