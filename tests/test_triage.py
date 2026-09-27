from __future__ import annotations

from pathlib import Path

from rag_eval_harness.agent.triage import MAX_TEXT_CHARS, triage
from rag_eval_harness.regression.compare import compare_means, load_means_ref, load_rows_ref
from rag_eval_harness.types import RowScore, compute_means

NIMBUS = Path(__file__).resolve().parents[1] / "examples" / "nimbus"


def _row(question: str, contexts: list[str], **metrics: float) -> RowScore:
    return RowScore(
        question=question,
        answer=f"answer to {question}",
        retrieved_contexts=contexts,
        ground_truth=f"truth for {question}",
        metrics=metrics,
    )


def _report(baseline: list[RowScore], head: list[RowScore]):
    return compare_means(compute_means(baseline), compute_means(head), threshold=0.05)


def test_triage_nimbus_weak_is_one_retrieval_group() -> None:
    _, b_means = load_means_ref(str(NIMBUS / "baseline.json"))
    _, h_means = load_means_ref(str(NIMBUS / "weak.json"))
    _, b_rows = load_rows_ref(str(NIMBUS / "baseline.json"))
    _, h_rows = load_rows_ref(str(NIMBUS / "weak.json"))
    report = compare_means(b_means, h_means, threshold=0.05)

    groups = triage(report, b_rows, h_rows, limit=5)

    assert [group.stage for group in groups] == ["retrieval"]
    assert [item.metric for item in groups[0].metrics] == ["context_recall"]
    rows = groups[0].rows
    assert len(rows) == 5
    assert rows[0].index == 31
    assert rows[0].drops == {"context_recall": (1.0, 0.0)}
    assert rows[0].lost_contexts and not rows[0].gained_contexts


def test_triage_passing_report_is_empty() -> None:
    rows = [_row("q", ["a"], context_recall=1.0)]
    assert triage(_report(rows, rows), rows, rows) == []


def test_triage_splits_stages_in_order() -> None:
    baseline = [
        _row("q0", ["a"], context_recall=1.0, faithfulness=1.0),
        _row("q1", ["b"], context_recall=1.0, faithfulness=1.0),
        _row("q2", ["c"], context_recall=1.0, faithfulness=1.0),
    ]
    head = [
        _row("q0", ["x"], context_recall=0.0, faithfulness=1.0),
        _row("q1", ["b"], context_recall=1.0, faithfulness=0.0),
        _row("q2", ["c"], context_recall=1.0, faithfulness=1.0),
    ]

    groups = triage(_report(baseline, head), baseline, head)

    assert [group.stage for group in groups] == ["retrieval", "generation"]
    assert [row.index for row in groups[0].rows] == [0]
    assert groups[0].rows[0].lost_contexts == ["a"]
    assert groups[0].rows[0].gained_contexts == ["x"]
    assert [row.index for row in groups[1].rows] == [1]


def test_triage_unknown_metric_is_other_and_respects_limit() -> None:
    baseline = [_row(f"q{i}", ["a"], bleu=1.0) for i in range(4)]
    head = [_row(f"q{i}", ["a"], bleu=0.5 - i / 10) for i in range(4)]

    groups = triage(_report(baseline, head), baseline, head, limit=2)

    assert [group.stage for group in groups] == ["other"]
    assert [row.index for row in groups[0].rows] == [3, 2]


def test_triage_clips_long_text() -> None:
    long = "x" * (MAX_TEXT_CHARS * 2)
    baseline = [_row("q", [long], context_recall=1.0)]
    head = [_row("q", [], context_recall=0.0)]

    groups = triage(_report(baseline, head), baseline, head)

    lost = groups[0].rows[0].lost_contexts[0]
    assert len(lost) == MAX_TEXT_CHARS
    assert lost.endswith("...")
