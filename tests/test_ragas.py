from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from rag_eval_harness.evaluators.ragas import RagasEvaluator, RagasUnavailableError
from rag_eval_harness.types import METRIC_ANSWER_RELEVANCY, METRIC_FAITHFULNESS, EvalRow


class FakeMetric:
    def __init__(self, value: float, name: str = "m") -> None:
        self.value = value
        self.name = name
        self.calls: list[dict] = []

    async def ascore(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(value=self.value)


def test_ragas_adapter_uses_injected_metrics() -> None:
    faith = FakeMetric(0.9)
    rel = FakeMetric(0.8)
    prec = FakeMetric(0.7)
    rec = FakeMetric(0.6)
    evaluator = RagasEvaluator(
        metrics={
            "faithfulness": faith,
            "answer_relevancy": rel,
            "context_precision": prec,
            "context_recall": rec,
        }
    )
    rows = [
        EvalRow(question="Q", answer="A", retrieved_contexts=["c"], ground_truth="G"),
        EvalRow(question="Q2", answer="A2", retrieved_contexts=["c2"]),
    ]
    summary = evaluator.evaluate(rows)
    assert summary.means[METRIC_FAITHFULNESS] == pytest.approx(0.9)
    assert summary.means[METRIC_ANSWER_RELEVANCY] == pytest.approx(0.8)
    assert summary.rows[0].metrics["context_precision"] == 0.7
    assert "context_precision" not in summary.rows[1].metrics
    assert "reference" not in faith.calls[0]
    assert "reference" in prec.calls[0]
    assert len(prec.calls) == 1


def test_ragas_unavailable_without_extra() -> None:
    def boom():
        raise RagasUnavailableError("missing extra")

    evaluator = RagasEvaluator(metric_factory=boom)
    with pytest.raises(RagasUnavailableError):
        evaluator.evaluate([EvalRow(question="Q", answer="A")])


@pytest.mark.skipif(not os.environ.get("OPENAI_API_KEY"), reason="requires OPENAI_API_KEY")
def test_ragas_optional_live_judge() -> None:
    """Gated integration: only runs when OPENAI_API_KEY is present."""
    from rag_eval_harness.evaluators.ragas import RagasEvaluator as Live

    summary = Live().evaluate(
        [
            EvalRow(
                question="What is 2+2?",
                answer="4",
                retrieved_contexts=["2+2=4"],
                ground_truth="4",
            )
        ]
    )
    assert METRIC_FAITHFULNESS in summary.means
