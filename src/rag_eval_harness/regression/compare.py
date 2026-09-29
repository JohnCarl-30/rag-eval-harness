from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import RowScore

DEFAULT_THRESHOLD = 0.05


@dataclass
class MetricDelta:
    metric: str
    baseline: float
    head: float
    delta: float
    dropped: bool


@dataclass
class RegressionReport:
    passed: bool
    threshold: float
    baseline_ref: str
    head_ref: str
    deltas: list[MetricDelta] = field(default_factory=list)
    baseline_errors: int | None = None
    head_errors: int | None = None

    @property
    def errors_increased(self) -> bool:
        # Means skip errored rows, so a SUT that times out on most rows can keep
        # its means. More errors than the baseline is a regression in its own right.
        if self.baseline_errors is None or self.head_errors is None:
            return False
        return self.head_errors > self.baseline_errors

    def failing(self) -> list[MetricDelta]:
        return [item for item in self.deltas if item.dropped]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "threshold": self.threshold,
            "baseline_ref": self.baseline_ref,
            "head_ref": self.head_ref,
            "baseline_errors": self.baseline_errors,
            "head_errors": self.head_errors,
            "errors_increased": self.errors_increased,
            "deltas": [
                {
                    "metric": item.metric,
                    "baseline": item.baseline,
                    "head": item.head,
                    "delta": item.delta,
                    "dropped": item.dropped,
                }
                for item in self.deltas
            ],
        }


def compare_means(
    baseline: dict[str, float],
    head: dict[str, float],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    baseline_ref: str = "baseline",
    head_ref: str = "head",
    baseline_errors: int | None = None,
    head_errors: int | None = None,
) -> RegressionReport:
    deltas: list[MetricDelta] = []
    for metric, base_value in sorted(baseline.items()):
        head_value = float(head.get(metric, 0.0))
        delta = round(head_value - float(base_value), 6)
        dropped = (float(base_value) - head_value) > threshold
        deltas.append(
            MetricDelta(
                metric=metric,
                baseline=float(base_value),
                head=head_value,
                delta=delta,
                dropped=dropped,
            )
        )
    report = RegressionReport(
        passed=True,
        threshold=threshold,
        baseline_ref=baseline_ref,
        head_ref=head_ref,
        deltas=deltas,
        baseline_errors=baseline_errors,
        head_errors=head_errors,
    )
    report.passed = not any(item.dropped for item in deltas) and not report.errors_increased
    return report


def _means_from_payload(payload: dict[str, Any]) -> dict[str, float]:
    means = payload.get("means", payload)
    if not isinstance(means, dict):
        raise ValueError("Baseline/head JSON must contain a means object")
    return {str(key): float(value) for key, value in means.items() if key != "rows"}


@dataclass
class RowMetricDelta:
    index: int
    question: str
    metric: str
    baseline: float
    head: float
    drop: float


def load_rows_ref(ref: str, store: Store | None = None) -> tuple[str, list[RowScore]]:
    path = Path(ref)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{ref} must be a JSON object")
        raw_rows = payload.get("rows")
        if not isinstance(raw_rows, list):
            raise ValueError(
                f"{ref} has no per-row scores; pass a run id or a snapshot from rag-eval eval -o"
            )
        return ref, [RowScore.from_dict(item) for item in raw_rows if isinstance(item, dict)]
    if store is None:
        raise ValueError(f"{ref} is not a file and no store was provided to look up a run id")
    run = store.get_run(ref)
    if run is None:
        raise KeyError(f"Run not found: {ref}")
    return ref, store.get_run_scores(ref)


def pair_rows(
    baseline: list[RowScore], head: list[RowScore]
) -> list[tuple[RowScore | None, RowScore | None]]:
    """Match rows by question text, in head order.

    Baseline and head are separate uploads, so a reordered or edited golden set
    must not compare unrelated questions. Repeated questions pair in order.
    Unmatched baseline rows come last with no head.
    """
    by_question: dict[str, list[int]] = {}
    for index, row in enumerate(baseline):
        by_question.setdefault(row.question.strip(), []).append(index)
    used: set[int] = set()
    pairs: list[tuple[RowScore | None, RowScore | None]] = []
    for right in head:
        queue = by_question.get(right.question.strip())
        if queue:
            index = queue.pop(0)
            used.add(index)
            pairs.append((baseline[index], right))
        else:
            pairs.append((None, right))
    pairs.extend((left, None) for index, left in enumerate(baseline) if index not in used)
    return pairs


def worst_row_drops(
    baseline: list[RowScore],
    head: list[RowScore],
    *,
    metric: str | None = None,
    limit: int = 8,
) -> list[RowMetricDelta]:
    drops: list[RowMetricDelta] = []
    for index, (left, right) in enumerate(pair_rows(baseline, head)):
        if left is None or right is None:
            continue
        names = [metric] if metric else sorted(set(left.metrics) | set(right.metrics))
        for name in names:
            if not name:
                continue
            if name not in left.metrics or name not in right.metrics:
                continue
            base_value = float(left.metrics[name])
            head_value = float(right.metrics[name])
            drop = round(base_value - head_value, 6)
            if drop <= 0:
                continue
            drops.append(
                RowMetricDelta(
                    index=index,
                    question=right.question,
                    metric=name,
                    baseline=base_value,
                    head=head_value,
                    drop=drop,
                )
            )
    drops.sort(key=lambda item: item.drop, reverse=True)
    return drops[:limit]


def load_means_ref(ref: str, store: Store | None = None) -> tuple[str, dict[str, float]]:
    path = Path(ref)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{ref} must be a JSON object")
        return ref, _means_from_payload(payload)
    if store is None:
        raise ValueError(f"{ref} is not a file and no store was provided to look up a run id")
    run = store.get_run(ref)
    if run is None:
        raise KeyError(f"Run not found: {ref}")
    if not run.means:
        raise ValueError(f"Run {ref} has no means (status={run.status})")
    return ref, {str(key): float(value) for key, value in run.means.items()}


def load_errors_ref(ref: str, store: Store | None = None) -> int | None:
    """Error count for a run id or snapshot. None when a means-only file has none."""
    path = Path(ref)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{ref} must be a JSON object")
        if "error_count" in payload:
            return int(payload["error_count"] or 0)
        rows = payload.get("rows")
        if isinstance(rows, list):
            return sum(1 for row in rows if isinstance(row, dict) and row.get("error"))
        return None
    if store is None:
        raise ValueError(f"{ref} is not a file and no store was provided to look up a run id")
    run = store.get_run(ref)
    if run is None:
        raise KeyError(f"Run not found: {ref}")
    return run.error_count
