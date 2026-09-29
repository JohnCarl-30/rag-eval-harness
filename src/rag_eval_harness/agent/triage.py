from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from rag_eval_harness.regression.compare import (
    MetricDelta,
    RegressionReport,
    pair_rows,
    worst_row_drops,
)
from rag_eval_harness.types import (
    METRIC_ANSWER_RELEVANCY,
    METRIC_CONTEXT_PRECISION,
    METRIC_CONTEXT_RECALL,
    METRIC_FAITHFULNESS,
    RowScore,
)

Stage = Literal["retrieval", "generation", "other"]

STAGE_BY_METRIC: dict[str, Stage] = {
    METRIC_CONTEXT_RECALL: "retrieval",
    METRIC_CONTEXT_PRECISION: "retrieval",
    METRIC_FAITHFULNESS: "generation",
    METRIC_ANSWER_RELEVANCY: "generation",
}
STAGE_ORDER: tuple[Stage, ...] = ("retrieval", "generation", "other")

MAX_TEXT_CHARS = 800
MAX_CONTEXTS = 4


def _clip(text: str | None) -> str | None:
    if text is None or len(text) <= MAX_TEXT_CHARS:
        return text
    return text[: MAX_TEXT_CHARS - 3] + "..."


@dataclass
class RowEvidence:
    index: int
    question: str
    ground_truth: str | None
    drops: dict[str, tuple[float, float]]
    baseline_answer: str | None
    head_answer: str | None
    lost_contexts: list[str] = field(default_factory=list)
    gained_contexts: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "question": self.question,
            "drops": {name: list(pair) for name, pair in self.drops.items()},
        }


@dataclass
class FailureGroup:
    """Failing means that share a pipeline stage, plus the rows that dropped most."""

    stage: Stage
    metrics: list[MetricDelta]
    rows: list[RowEvidence]

    def to_dict(self) -> dict[str, Any]:
        return {
            "stage": self.stage,
            "metrics": [item.metric for item in self.metrics],
            "rows": [row.to_dict() for row in self.rows],
        }


def row_evidence(
    index: int,
    baseline: RowScore,
    head: RowScore,
    drops: dict[str, tuple[float, float]],
) -> RowEvidence:
    before = set(baseline.retrieved_contexts)
    after = set(head.retrieved_contexts)
    lost = [text for text in baseline.retrieved_contexts if text not in after]
    gained = [text for text in head.retrieved_contexts if text not in before]
    return RowEvidence(
        index=index,
        question=head.question or baseline.question,
        ground_truth=_clip(head.ground_truth or baseline.ground_truth),
        drops=drops,
        baseline_answer=_clip(baseline.answer),
        head_answer=_clip(head.answer),
        lost_contexts=[_clip(text) or "" for text in lost[:MAX_CONTEXTS]],
        gained_contexts=[_clip(text) or "" for text in gained[:MAX_CONTEXTS]],
    )


def triage(
    report: RegressionReport,
    baseline: list[RowScore],
    head: list[RowScore],
    *,
    limit: int = 5,
) -> list[FailureGroup]:
    """Group failing means by stage and attach the worst-dropping rows for each group.

    Rows pair by question, the same as `rag-eval diff`; a row index is its position in
    `pair_rows`, which is the head row's position. A stage with failing means but no
    row that dropped is skipped, since there is nothing to show a model.
    """
    by_stage: dict[Stage, list[MetricDelta]] = {}
    for item in report.failing():
        by_stage.setdefault(STAGE_BY_METRIC.get(item.metric, "other"), []).append(item)

    groups: list[FailureGroup] = []
    for stage in STAGE_ORDER:
        metrics = by_stage.get(stage)
        if not metrics:
            continue
        per_row: dict[int, dict[str, tuple[float, float]]] = {}
        worst: dict[int, float] = {}
        for item in metrics:
            for drop in worst_row_drops(baseline, head, metric=item.metric, limit=len(head)):
                per_row.setdefault(drop.index, {})[drop.metric] = (drop.baseline, drop.head)
                worst[drop.index] = max(worst.get(drop.index, 0.0), drop.drop)
        ranked = sorted(worst, key=lambda index: (-worst[index], index))[:limit]
        pairs = pair_rows(baseline, head)
        rows = [row_evidence(index, *pairs[index], per_row[index]) for index in ranked]
        if rows:
            groups.append(FailureGroup(stage=stage, metrics=metrics, rows=rows))
    return groups
