from __future__ import annotations

import pytest

from rag_eval_harness.engine import eval_from_path, run_eval
from rag_eval_harness.io import RowCapError
from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import ROW_CAP, EvalRow


def test_http_eval_uses_adapter(store: Store, golden_csv, monkeypatch) -> None:
    from rag_eval_harness import engine as engine_mod

    class FakeHttp:
        def __init__(self, url, **kwargs):
            self.url = url

        def run(self, rows):
            return [
                EvalRow(
                    question=row.question,
                    answer=f"ans:{row.question[:12]}",
                    retrieved_contexts=["ctx"],
                    ground_truth=row.ground_truth,
                )
                for row in rows
            ]

    monkeypatch.setattr(engine_mod, "HttpAdapter", FakeHttp)
    run, summary = eval_from_path(
        store, golden_csv, sut_url="http://dummy-rag:8080/query", evaluator="stub"
    )
    assert run.adapter_type == "http"
    assert run.status == "completed"
    assert summary.error_count == 0
    assert all(row.answer.startswith("ans:") for row in summary.rows)


def test_engine_row_cap(store: Store) -> None:
    rows = [EvalRow(question=f"q{i}", answer="a") for i in range(ROW_CAP + 1)]
    with pytest.raises(RowCapError):
        run_eval(
            store,
            rows,
            dataset_name="too-big",
            adapter_type="traces",
            evaluator="stub",
        )


def test_failed_setup_marks_run(store: Store) -> None:
    rows = [EvalRow(question="Q", answer="A")]
    dataset = store.create_dataset(rows, name="d")
    run = store.create_run(
        dataset_id=dataset.id,
        adapter_type="nope",
        evaluator="stub",
    )
    from rag_eval_harness.engine import execute_run

    with pytest.raises(ValueError):
        execute_run(store, run.id)
    assert store.get_run(run.id).status == "failed"
