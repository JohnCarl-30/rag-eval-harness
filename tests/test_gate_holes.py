"""A worse head must not pass the gate by refusing, skipping questions, or switching evaluator."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from typer.testing import CliRunner

from rag_eval_harness.api.app import create_app
from rag_eval_harness.cli import app
from rag_eval_harness.engine import run_eval
from rag_eval_harness.regression.compare import (
    RunSide,
    compare_means,
    compare_runs,
    evaluator_mismatch,
    load_side,
)
from rag_eval_harness.regression.markdown import gate_markdown
from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import EvalRow, RowScore

runner = CliRunner()


def _rows(count: int = 20) -> list[dict]:
    return [
        {
            "question": f"How do I reset setting {n}?",
            "ground_truth": f"Open panel {n} and press reset.",
            "answer": f"Open panel {n} and press reset.",
            "retrieved_contexts": [f"To reset setting {n}: open panel {n} and press reset."],
        }
        for n in range(10, 10 + count)
    ]


def _refusing(rows: list[dict], keep: int) -> list[dict]:
    refused = [{**row, "answer": "Sorry, I can't help.", "abstained": True} for row in rows[keep:]]
    return rows[:keep] + refused


def _snapshot(tmp_path: Path, name: str, rows: list[dict], evaluator: str = "lexical") -> Path:
    traces = tmp_path / f"{name}.jsonl"
    traces.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    out = tmp_path / f"{name}.json"
    result = runner.invoke(
        app,
        [
            "eval",
            str(traces),
            "--evaluator",
            evaluator,
            "-o",
            str(out),
            "--db",
            f"sqlite:///{tmp_path / 'gate.db'}",
        ],
    )
    assert result.exit_code == 0, result.output
    return out


def _regress(tmp_path: Path, baseline: Path, head: Path, *extra: str):
    db_url = f"sqlite:///{tmp_path / 'gate.db'}"
    return runner.invoke(
        app, ["regress", "--baseline", str(baseline), "--head", str(head), "--db", db_url, *extra]
    )


def test_head_that_refuses_most_answers_fails(tmp_path) -> None:
    baseline = _snapshot(tmp_path, "base", _rows())
    head = _snapshot(tmp_path, "head", _refusing(_rows(), keep=2))

    result = _regress(tmp_path, baseline, head)

    assert result.exit_code == 1, result.output
    assert "abstained rows       baseline=0/20  head=18/20  FAIL" in result.output
    # The means alone still look healthy: this is the hole the check closes.
    assert "faithfulness         baseline=1.0000  head=1.0000  delta=+0.0000  ok" in result.output


def test_abstained_share_within_threshold_passes(tmp_path) -> None:
    baseline = _snapshot(tmp_path, "base", _rows())
    head = _snapshot(tmp_path, "head", _refusing(_rows(), keep=19))

    result = _regress(tmp_path, baseline, head)

    assert result.exit_code == 0, result.output
    assert "abstained rows       baseline=0/20  head=1/20  ok" in result.output


def test_abstained_check_uses_shares_and_skips_unknown_counts() -> None:
    means = {"faithfulness": 0.9}
    same_share = compare_means(
        means,
        means,
        baseline_abstained=5,
        head_abstained=10,
        baseline_rows=20,
        head_rows=40,
    )
    assert same_share.passed is True
    unknown = compare_means(means, means, head_abstained=10, baseline_rows=20, head_rows=20)
    assert unknown.abstained_increased is False
    assert unknown.passed is True


def test_snapshot_without_abstained_fields_skips_the_check(tmp_path) -> None:
    # Snapshots written by 0.3.0 and earlier do not say which rows abstained.
    old = tmp_path / "old.json"
    row = {"question": "Q", "answer": "A", "retrieved_contexts": [], "metrics": {"mrr": 1.0}}
    old.write_text(json.dumps({"means": {"mrr": 1.0}, "rows": [row]}), encoding="utf-8")
    assert load_side(str(old)).abstained is None

    new = tmp_path / "new.json"
    new.write_text(
        json.dumps({"means": {"mrr": 1.0}, "rows": [{**row, "abstained": True}]}), encoding="utf-8"
    )
    assert load_side(str(new)).abstained == 1


def test_head_missing_baseline_questions_fails(tmp_path) -> None:
    baseline = _snapshot(tmp_path, "base", _rows())
    head = _snapshot(tmp_path, "head", _rows()[:2])

    result = _regress(tmp_path, baseline, head)

    assert result.exit_code == 1, result.output
    assert "questions covered    baseline=20/20  head=2/20  FAIL" in result.output


def test_reordered_and_extended_head_still_passes(tmp_path) -> None:
    extra = {
        "question": "A brand new question?",
        "ground_truth": "A brand new answer.",
        "answer": "A brand new answer.",
        "retrieved_contexts": ["A brand new question has a brand new answer."],
    }
    baseline = _snapshot(tmp_path, "base", _rows())
    head = _snapshot(tmp_path, "head", [extra, *reversed(_rows())])

    result = _regress(tmp_path, baseline, head)

    assert result.exit_code == 0, result.output
    assert "questions covered" not in result.output


def test_coverage_check_needs_rows_on_both_sides() -> None:
    row = RowScore(
        question="Q", answer="A", retrieved_contexts=[], ground_truth=None, metrics={"mrr": 1.0}
    )
    with_rows = RunSide(ref="a", means={"mrr": 1.0}, rows=[row])
    means_only = RunSide(ref="b", means={"mrr": 1.0})

    assert compare_runs(with_rows, means_only).missing_questions is None
    assert compare_runs(with_rows, RunSide(ref="c", means={"mrr": 1.0}, rows=[])).passed is False


def test_regress_refuses_to_compare_two_evaluators(tmp_path) -> None:
    baseline = _snapshot(tmp_path, "base", _rows(), evaluator="stub")
    head = _snapshot(tmp_path, "head", _rows(), evaluator="lexical")

    result = _regress(tmp_path, baseline, head)

    assert result.exit_code == 2, result.output
    assert "'stub'" in result.output and "'lexical'" in result.output
    assert "FAIL" not in result.output


def test_diff_warns_but_still_compares_two_evaluators(tmp_path) -> None:
    baseline = _snapshot(tmp_path, "base", _rows(), evaluator="stub")
    head = _snapshot(tmp_path, "head", _rows(), evaluator="lexical")

    result = runner.invoke(
        app,
        [
            "diff",
            "--baseline",
            str(baseline),
            "--head",
            str(head),
            "--db",
            f"sqlite:///{tmp_path / 'gate.db'}",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "warning: Baseline was scored with the 'stub' evaluator" in result.output
    assert "faithfulness" in result.output


def test_evaluator_check_skipped_for_means_only_files() -> None:
    known = RunSide(ref="a", means={}, evaluator="lexical")
    assert evaluator_mismatch(known, RunSide(ref="b", means={})) is None
    assert evaluator_mismatch(known, RunSide(ref="b", means={}, evaluator="lexical")) is None
    assert evaluator_mismatch(known, RunSide(ref="b", means={}, evaluator="ragas"))


def test_metric_missing_from_head_fails_and_new_metric_is_shown() -> None:
    report = compare_means({"faithfulness": 0.02}, {"mrr": 0.7}, threshold=0.05)

    assert report.passed is False
    assert report.deltas[0].missing is True
    assert report.new_metrics == {"mrr": 0.7}
    text_report = gate_markdown(report)
    assert "| faithfulness | 0.0200 | missing | | **FAIL** |" in text_report
    assert "| mrr | n/a | 0.7000 | | new, not gated |" in text_report


def test_markdown_report_lists_abstained_and_missing_rows() -> None:
    means = {"faithfulness": 0.9}
    report = compare_means(
        means,
        means,
        baseline_abstained=0,
        head_abstained=6,
        baseline_rows=20,
        head_rows=12,
        missing_questions=8,
    )

    text_report = gate_markdown(report)

    assert text_report.startswith("### rag-eval: ❌ Regression detected")
    assert "| abstained rows | 0/20 | 6/12 | | **FAIL** |" in text_report
    assert "| questions covered | 20/20 | 12/20 | | **FAIL** |" in text_report


def test_store_keeps_abstained_and_gates_run_ids(store: Store) -> None:
    def rows(refusals: int) -> list[EvalRow]:
        return [
            EvalRow(
                question=f"Question {n}?",
                answer="Sorry." if n < refusals else f"Answer {n}.",
                retrieved_contexts=[f"Answer {n}."],
                abstained=n < refusals,
            )
            for n in range(10)
        ]

    base_run, _ = run_eval(store, rows(0), dataset_name="base", adapter_type="traces")
    head_run, summary = run_eval(store, rows(4), dataset_name="head", adapter_type="traces")

    assert summary.abstained_count == 4
    assert store.get_run(head_run.id).abstained_count == 4
    assert [row.abstained for row in store.get_run_scores(head_run.id)][:5] == [True] * 4 + [False]
    report = compare_runs(load_side(base_run.id, store), load_side(head_run.id, store))
    assert report.abstained_increased is True
    assert report.passed is False


def test_older_database_gains_abstained_columns(tmp_path) -> None:
    url = f"sqlite:///{tmp_path / 'old.db'}"
    store = Store(url)
    dataset = store.create_dataset([EvalRow(question="Q", answer="A")], name="d")
    run, _ = run_eval(
        store, store.get_dataset_rows(dataset.id), dataset_name="d", adapter_type="traces"
    )
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE runs DROP COLUMN abstained_count"))
        connection.execute(text("ALTER TABLE run_scores DROP COLUMN abstained"))
    engine.dispose()

    reopened = Store(url)

    # A run scored before the column existed has an unknown count, not zero.
    assert reopened.get_run(run.id).abstained_count is None
    assert load_side(run.id, reopened).abstained is None
    assert reopened.get_run_scores(run.id)[0].abstained is False


@pytest.mark.parametrize("refusals,passed", [(0, True), (6, False)])
def test_api_diff_reports_abstained_check(store: Store, refusals: int, passed: bool) -> None:
    def rows(count: int) -> list[EvalRow]:
        return [
            EvalRow(
                question=f"Question {n}?",
                answer="Sorry." if n < count else f"Answer {n}.",
                retrieved_contexts=[f"Answer {n}."],
                abstained=n < count,
            )
            for n in range(10)
        ]

    base_run, _ = run_eval(store, rows(0), dataset_name="base", adapter_type="traces")
    head_run, _ = run_eval(
        store, rows(refusals), dataset_name="head", adapter_type="traces", evaluator="stub"
    )
    client = TestClient(create_app(store, bind_host="127.0.0.1"))

    body = client.get(f"/api/runs/{head_run.id}/diff", params={"against": base_run.id}).json()

    assert body["passed"] is passed
    check = next(item for item in body["checks"] if item["label"] == "abstained rows")
    assert check == {
        "label": "abstained rows",
        "baseline": "0/10",
        "head": f"{refusals}/10",
        "failed": not passed,
    }
    assert body["warnings"] == []
    assert body["head"]["abstained_count"] == refusals


def test_api_diff_warns_on_two_evaluators(store: Store) -> None:
    rows = [EvalRow(question="Q?", answer="A.", retrieved_contexts=["A."])]
    base_run, _ = run_eval(store, rows, dataset_name="d", adapter_type="traces", evaluator="stub")
    head_run, _ = run_eval(
        store, rows, dataset_name="d", adapter_type="traces", evaluator="lexical"
    )
    client = TestClient(create_app(store, bind_host="127.0.0.1"))

    body = client.get(f"/api/runs/{head_run.id}/diff", params={"against": base_run.id}).json()

    assert len(body["warnings"]) == 1
    assert "'stub'" in body["warnings"][0]
