from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from rag_eval_harness.engine import eval_from_path
from rag_eval_harness.evaluators.lexical import LexicalEvaluator
from rag_eval_harness.evaluators.ragas import RagasEvaluator
from rag_eval_harness.evaluators.retrieval import retrieval_metrics
from rag_eval_harness.io import load_text
from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import EvalRow

WORKSPACE = "What is a Nimbus workspace?\n\nA workspace holds your projects and bill."
BILLING = "How billing works\n\nNimbus bills seats and events."
SSO = "Set up SSO\n\nGo to Settings, Security, SSO."


def test_labels_score_share_found_and_first_rank() -> None:
    row = EvalRow(
        question="q",
        retrieved_contexts=[SSO, BILLING, WORKSPACE],
        reference_contexts=["what is a  NIMBUS workspace?", "Data retention"],
    )
    assert retrieval_metrics(row) == {"recall_at_k": 0.5, "mrr": 0.3333}


def test_labels_miss_scores_zero() -> None:
    row = EvalRow(question="q", retrieved_contexts=[SSO], reference_contexts=["How billing works"])
    assert retrieval_metrics(row) == {"recall_at_k": 0.0, "mrr": 0.0}


def test_ground_truth_fallback_finds_covering_passage() -> None:
    row = EvalRow(
        question="q",
        retrieved_contexts=[SSO, WORKSPACE],
        ground_truth="A workspace holds your projects and bill.",
    )
    assert retrieval_metrics(row) == {"recall_at_k": 1.0, "mrr": 0.5}


def test_ground_truth_fallback_miss_and_labels_take_priority() -> None:
    miss = EvalRow(question="q", retrieved_contexts=[SSO], ground_truth="Nimbus bills seats.")
    assert retrieval_metrics(miss) == {"recall_at_k": 0.0, "mrr": 0.0}
    labelled = EvalRow(
        question="q",
        retrieved_contexts=[SSO],
        ground_truth="Go to Settings, Security, SSO.",
        reference_contexts=["How billing works"],
    )
    assert retrieval_metrics(labelled) == {"recall_at_k": 0.0, "mrr": 0.0}


def test_no_labels_and_no_ground_truth_skips_retrieval_metrics() -> None:
    assert retrieval_metrics(EvalRow(question="q", retrieved_contexts=[SSO])) == {}


def test_lexical_reports_retrieval_metrics_and_means() -> None:
    summary = LexicalEvaluator().evaluate(
        [
            EvalRow(
                question="q1", answer="a", retrieved_contexts=[WORKSPACE], ground_truth=WORKSPACE
            ),
            EvalRow(question="q2", answer="a", retrieved_contexts=[SSO], ground_truth=BILLING),
        ]
    )
    assert summary.rows[0].metrics["mrr"] == 1.0
    assert summary.means["recall_at_k"] == 0.5


def test_ragas_adds_retrieval_metrics_but_keeps_judge_failures_as_errors() -> None:
    class Metric:
        def __init__(self, fail: bool) -> None:
            self.fail = fail

        async def ascore(self, **kwargs):
            if self.fail:
                raise RuntimeError("judge down")
            return SimpleNamespace(value=0.5)

    row = EvalRow(question="q", answer="a", retrieved_contexts=[WORKSPACE], ground_truth=WORKSPACE)
    names = ("faithfulness", "answer_relevancy", "context_precision", "context_recall")

    ok = RagasEvaluator(metrics={name: Metric(False) for name in names}).evaluate([row])
    assert ok.rows[0].metrics["recall_at_k"] == 1.0

    down = RagasEvaluator(metrics={name: Metric(True) for name in names}).evaluate([row])
    assert down.rows[0].error
    assert down.rows[0].metrics == {}


def test_reference_contexts_column_parses_with_alias() -> None:
    rows = load_text(
        "question,ground_truth,relevant_contexts\n"
        "q,gt,What is a Nimbus workspace?|Data retention\n",
        filename="golden.csv",
    )
    assert rows[0].reference_contexts == ["What is a Nimbus workspace?", "Data retention"]


def test_labels_and_abstained_survive_the_store(tmp_path) -> None:
    traces = tmp_path / "traces.jsonl"
    traces.write_text(
        "\n".join(
            json.dumps(record)
            for record in (
                {
                    "question": "What is a workspace?",
                    "answer": "A workspace holds projects.",
                    "retrieved_contexts": [SSO, WORKSPACE],
                    "ground_truth": "A workspace holds your projects.",
                    "reference_contexts": ["What is a Nimbus workspace?"],
                },
                {
                    "question": "Can I pay with crypto?",
                    "answer": "I can't help with that, a person will follow up.",
                    "retrieved_contexts": [BILLING],
                    "abstained": True,
                },
            )
        ),
        encoding="utf-8",
    )
    store = Store(f"sqlite:///{tmp_path / 'r.db'}")

    run, summary = eval_from_path(store, traces, evaluator="lexical")

    rows = store.get_dataset_rows(run.dataset_id)
    assert rows[0].reference_contexts == ["What is a Nimbus workspace?"]
    assert rows[1].abstained is True
    assert summary.rows[0].metrics["mrr"] == 0.5
    assert "faithfulness" not in summary.rows[1].metrics


def test_store_adds_new_columns_to_an_older_database(tmp_path) -> None:
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE datasets (
                id VARCHAR(36) PRIMARY KEY, name VARCHAR(256) NOT NULL, filename VARCHAR(512),
                row_count INTEGER NOT NULL, created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE dataset_rows (
                id VARCHAR(36) PRIMARY KEY, dataset_id VARCHAR(36) NOT NULL,
                row_index INTEGER NOT NULL, question TEXT NOT NULL, ground_truth TEXT,
                answer TEXT, retrieved_contexts JSON NOT NULL
            );
            INSERT INTO datasets (id, name, row_count) VALUES ('d1', 'old', 1);
            INSERT INTO dataset_rows VALUES ('r1', 'd1', 0, 'q', 'gt', 'a', '["c"]');
            """
        )

    store = Store(f"sqlite:///{path}")

    [row] = store.get_dataset_rows("d1")
    assert row.question == "q"
    assert row.abstained is False
    assert row.reference_contexts == []
