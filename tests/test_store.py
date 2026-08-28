from __future__ import annotations

from rag_eval_harness.engine import eval_from_path
from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import EvalRow


def test_create_dataset_and_run(store: Store) -> None:
    rows = [
        EvalRow(question="Q1", answer="A1", retrieved_contexts=["c"], ground_truth="G1"),
        EvalRow(question="Q2", answer="A2", retrieved_contexts=["c2"]),
    ]
    dataset = store.create_dataset(rows, name="demo", filename="demo.csv")
    assert dataset.row_count == 2
    loaded = store.get_dataset_rows(dataset.id)
    assert loaded[0].question == "Q1"
    assert loaded[1].ground_truth is None

    run = store.create_run(
        dataset_id=dataset.id,
        adapter_type="traces",
        evaluator="stub",
        label="t1",
        git_sha="abc",
    )
    assert run.status == "queued"
    listed = store.list_runs()
    assert listed[0].id == run.id


def test_baseline_is_unique_per_dataset(store: Store) -> None:
    rows = [EvalRow(question="Q", answer="A")]
    dataset = store.create_dataset(rows, name="d")
    a = store.create_run(dataset_id=dataset.id, adapter_type="traces", evaluator="stub")
    b = store.create_run(dataset_id=dataset.id, adapter_type="traces", evaluator="stub")
    store.set_baseline(a.id)
    store.set_baseline(b.id)
    assert store.get_run(a.id).is_baseline is False
    assert store.get_run(b.id).is_baseline is True


def test_eval_from_traces_persists_means(store: Store, traces_jsonl) -> None:
    run, summary = eval_from_path(store, traces_jsonl, evaluator="stub")
    assert run.status == "completed"
    assert summary.error_count == 0
    assert "faithfulness" in run.means
    assert "answer_relevancy" in run.means
    assert "context_precision" in run.means
    assert len(store.get_run_scores(run.id)) == 16
    assert store.list_datasets()[0].row_count == 16
