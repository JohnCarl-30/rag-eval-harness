from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ROW_CAP = 100

METRIC_FAITHFULNESS = "faithfulness"
METRIC_ANSWER_RELEVANCY = "answer_relevancy"
METRIC_CONTEXT_PRECISION = "context_precision"
METRIC_CONTEXT_RECALL = "context_recall"
METRIC_RECALL_AT_K = "recall_at_k"
METRIC_MRR = "mrr"

ALWAYS_METRICS: tuple[str, ...] = (METRIC_FAITHFULNESS, METRIC_ANSWER_RELEVANCY)
GROUND_TRUTH_METRICS: tuple[str, ...] = (METRIC_CONTEXT_PRECISION, METRIC_CONTEXT_RECALL)
RETRIEVAL_METRICS: tuple[str, ...] = (METRIC_RECALL_AT_K, METRIC_MRR)

RunStatus = Literal["queued", "running", "completed", "failed"]
AdapterType = Literal["traces", "http"]
EvaluatorName = Literal["stub", "lexical", "ragas"]

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "question": ("question", "user_input"),
    "ground_truth": ("ground_truth", "reference"),
    "answer": ("answer", "response"),
    "retrieved_contexts": ("retrieved_contexts", "contexts"),
    "abstained": ("abstained", "escalated"),
    "reference_contexts": ("reference_contexts", "relevant_contexts"),
}


@dataclass
class EvalRow:
    question: str
    answer: str | None = None
    retrieved_contexts: list[str] = field(default_factory=list)
    ground_truth: str | None = None
    error: str | None = None
    # The SUT declined to answer (refused, or handed off to a human). Answer
    # metrics are skipped: a refusal is neither grounded nor ungrounded.
    abstained: bool = False
    # Labels for which passages count as relevant: a retrieved context matches when it
    # contains one of these (an article title, a doc ID). Drives recall_at_k and mrr.
    reference_contexts: list[str] = field(default_factory=list)

    def has_ground_truth(self) -> bool:
        return bool(self.ground_truth and self.ground_truth.strip())


def is_truthy(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


@dataclass
class RowScore:
    question: str
    answer: str | None
    retrieved_contexts: list[str]
    ground_truth: str | None
    metrics: dict[str, float]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "answer": self.answer,
            "retrieved_contexts": self.retrieved_contexts,
            "ground_truth": self.ground_truth,
            "metrics": self.metrics,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RowScore:
        return cls(
            question=str(data.get("question") or ""),
            answer=data.get("answer"),
            retrieved_contexts=list(data.get("retrieved_contexts") or []),
            ground_truth=data.get("ground_truth"),
            metrics={k: float(v) for k, v in (data.get("metrics") or {}).items()},
            error=data.get("error"),
        )


@dataclass
class MetricSummary:
    means: dict[str, float]
    rows: list[RowScore]
    error_count: int

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def to_dict(self) -> dict[str, Any]:
        return {
            "means": self.means,
            "error_count": self.error_count,
            "row_count": self.row_count,
            "rows": [row.to_dict() for row in self.rows],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MetricSummary:
        rows = [RowScore.from_dict(item) for item in data.get("rows") or []]
        return cls(
            means={k: float(v) for k, v in (data.get("means") or {}).items()},
            rows=rows,
            error_count=int(data.get("error_count") or 0),
        )


def metrics_for_rows(rows: list[EvalRow]) -> tuple[str, ...]:
    names = list(ALWAYS_METRICS)
    if any(row.has_ground_truth() for row in rows):
        names.extend(GROUND_TRUTH_METRICS)
    return tuple(names)


def compute_means(rows: list[RowScore]) -> dict[str, float]:
    ok = [row for row in rows if not row.error]
    if not ok:
        return dict.fromkeys(ALWAYS_METRICS, 0.0)
    buckets: dict[str, list[float]] = {}
    for row in ok:
        for name, value in row.metrics.items():
            buckets.setdefault(name, []).append(value)
    return {name: round(sum(values) / len(values), 6) for name, values in buckets.items()}
