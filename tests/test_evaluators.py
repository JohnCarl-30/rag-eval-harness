from __future__ import annotations

from rag_eval_harness.evaluators import get_evaluator
from rag_eval_harness.evaluators.lexical import LexicalEvaluator
from rag_eval_harness.evaluators.stub import StubEvaluator
from rag_eval_harness.types import EvalRow


def test_stub_is_deterministic_and_adaptive() -> None:
    rows = [
        EvalRow(question="Q1", answer="A1", retrieved_contexts=["c1"], ground_truth="G1"),
        EvalRow(question="Q2", answer="A2", retrieved_contexts=["c2"]),
    ]
    first = StubEvaluator().evaluate(rows)
    second = StubEvaluator().evaluate(rows)
    assert first.means == second.means
    assert 0.5 <= first.means["faithfulness"] <= 1.0
    assert 0.5 <= first.means["answer_relevancy"] <= 1.0
    assert "context_precision" in first.rows[0].metrics
    assert "context_recall" in first.rows[0].metrics
    assert "context_precision" not in first.rows[1].metrics
    assert first.error_count == 0


def test_stub_preserves_row_errors() -> None:
    rows = [EvalRow(question="Q", error="http adapter: timeout")]
    summary = StubEvaluator().evaluate(rows)
    assert summary.error_count == 1
    assert summary.rows[0].error == "http adapter: timeout"
    assert summary.means["faithfulness"] == 0.0


def test_lexical_rewards_grounded_extractive_answers() -> None:
    rows = [
        EvalRow(
            question="How many seats on Growth?",
            answer="Growth includes 10 seats and 10M events.",
            retrieved_contexts=["Growth (10 seats, 10M events)."],
            ground_truth="Growth includes 10 seats and 10M events.",
        ),
        EvalRow(
            question="How many seats on Growth?",
            answer="We support unlimited Salesforce sync.",
            retrieved_contexts=["Growth (10 seats, 10M events)."],
            ground_truth="Growth includes 10 seats and 10M events.",
        ),
    ]
    summary = LexicalEvaluator().evaluate(rows)
    assert summary.rows[0].metrics["faithfulness"] > summary.rows[1].metrics["faithfulness"]
    assert summary.rows[0].metrics["context_recall"] >= summary.rows[1].metrics["context_recall"]


def test_get_evaluator_lexical() -> None:
    assert get_evaluator("lexical").name == "lexical"


def test_abstained_rows_skip_answer_metrics() -> None:
    rows = [
        EvalRow(
            question="How many seats on Growth?",
            answer="Growth includes 10 seats.",
            retrieved_contexts=["Growth includes 10 seats and 10M events."],
            ground_truth="Growth includes 10 seats.",
        ),
        EvalRow(
            question="Can I pay with crypto?",
            answer="I don't have that in the help center.",
            retrieved_contexts=["Growth includes 10 seats and 10M events."],
            ground_truth="I don't have that in the help center.",
            abstained=True,
        ),
    ]
    for evaluator in (LexicalEvaluator(), StubEvaluator()):
        summary = evaluator.evaluate(rows)
        refused = summary.rows[1].metrics
        assert "faithfulness" not in refused
        assert "answer_relevancy" not in refused
        assert "context_recall" in refused
        assert summary.means["faithfulness"] == summary.rows[0].metrics["faithfulness"]
        assert summary.error_count == 0
