from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import RowScore, count_abstained

DEFAULT_THRESHOLD = 0.05


@dataclass
class MetricDelta:
    metric: str
    baseline: float
    head: float
    delta: float
    dropped: bool
    # Head has no value for this metric at all. Its head is reported as 0.0 and it
    # always fails: a metric that vanished cannot be shown not to have regressed.
    missing: bool = False


@dataclass
class RegressionReport:
    passed: bool
    threshold: float
    baseline_ref: str
    head_ref: str
    deltas: list[MetricDelta] = field(default_factory=list)
    baseline_errors: int | None = None
    head_errors: int | None = None
    baseline_abstained: int | None = None
    head_abstained: int | None = None
    baseline_rows: int | None = None
    head_rows: int | None = None
    # Baseline questions with no row in head. None when either side has no rows.
    missing_questions: int | None = None
    # Metrics only head has. Shown, never gated: there is nothing to compare them to.
    new_metrics: dict[str, float] = field(default_factory=dict)

    @property
    def errors_increased(self) -> bool:
        # Means skip errored rows, so a SUT that times out on most rows can keep
        # its means. More errors than the baseline is a regression in its own right.
        if self.baseline_errors is None or self.head_errors is None:
            return False
        return self.head_errors > self.baseline_errors

    @property
    def abstained_increased(self) -> bool:
        # Answer metrics skip abstained rows, so a SUT that starts refusing the hard
        # questions keeps its means. Refusing can be right, so this gates the share of
        # rows, under the same threshold as the means, not a strict count like errors.
        counts = (self.baseline_abstained, self.head_abstained)
        if None in counts or not self.baseline_rows or not self.head_rows:
            return False
        rise = self.head_abstained / self.head_rows - self.baseline_abstained / self.baseline_rows
        return round(rise, 6) > self.threshold

    @property
    def questions_missing(self) -> bool:
        # A head that only ran the easy questions keeps its means too.
        return bool(self.missing_questions)

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
            "baseline_abstained": self.baseline_abstained,
            "head_abstained": self.head_abstained,
            "baseline_rows": self.baseline_rows,
            "head_rows": self.head_rows,
            "abstained_increased": self.abstained_increased,
            "missing_questions": self.missing_questions,
            "new_metrics": self.new_metrics,
            "deltas": [
                {
                    "metric": item.metric,
                    "baseline": item.baseline,
                    "head": item.head,
                    "delta": item.delta,
                    "dropped": item.dropped,
                    "missing": item.missing,
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
    baseline_abstained: int | None = None,
    head_abstained: int | None = None,
    baseline_rows: int | None = None,
    head_rows: int | None = None,
    missing_questions: int | None = None,
) -> RegressionReport:
    deltas: list[MetricDelta] = []
    for metric, base_value in sorted(baseline.items()):
        missing = metric not in head
        head_value = 0.0 if missing else float(head[metric])
        delta = round(head_value - float(base_value), 6)
        dropped = missing or (float(base_value) - head_value) > threshold
        deltas.append(
            MetricDelta(
                metric=metric,
                baseline=float(base_value),
                head=head_value,
                delta=delta,
                dropped=dropped,
                missing=missing,
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
        baseline_abstained=baseline_abstained,
        head_abstained=head_abstained,
        baseline_rows=baseline_rows,
        head_rows=head_rows,
        missing_questions=missing_questions,
        new_metrics={
            name: float(value) for name, value in sorted(head.items()) if name not in baseline
        },
    )
    report.passed = not (
        any(item.dropped for item in deltas)
        or report.errors_increased
        or report.abstained_increased
        or report.questions_missing
    )
    return report


@dataclass
class RunSide:
    """One side of a comparison: a stored run or a JSON snapshot.

    Everything but the means is optional, because a hand-written means-only file is a
    valid baseline. A check whose inputs are missing is skipped, never guessed.
    """

    ref: str
    means: dict[str, float]
    errors: int | None = None
    abstained: int | None = None
    row_count: int | None = None
    evaluator: str | None = None
    rows: list[RowScore] | None = None


def load_side(ref: str, store: Store | None = None) -> RunSide:
    path = Path(ref)
    if path.is_file():
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"{ref} must be a JSON object")
        raw_rows = payload.get("rows")
        has_rows = isinstance(raw_rows, list)
        row_dicts = [item for item in raw_rows if isinstance(item, dict)] if has_rows else []
        rows = [RowScore.from_dict(item) for item in row_dicts] if has_rows else None
        errors: int | None = None
        if "error_count" in payload:
            errors = int(payload["error_count"] or 0)
        elif rows is not None:
            errors = sum(1 for row in rows if row.error)
        # Snapshots written before rows carried `abstained` say nothing about refusals.
        abstained: int | None = None
        if payload.get("abstained_count") is not None:
            abstained = int(payload["abstained_count"])
        elif rows is not None and any("abstained" in item for item in row_dicts):
            abstained = count_abstained(rows)
        row_count = payload.get("row_count")
        evaluator = payload.get("evaluator")
        return RunSide(
            ref=ref,
            means=_means_from_payload(payload),
            errors=errors,
            abstained=abstained,
            row_count=len(rows) if rows is not None else _int_or_none(row_count),
            evaluator=evaluator.strip().lower() if isinstance(evaluator, str) else None,
            rows=rows,
        )
    if store is None:
        raise ValueError(f"{ref} is not a file and no store was provided to look up a run id")
    run = store.get_run(ref)
    if run is None:
        raise KeyError(f"Run not found: {ref}")
    if not run.means:
        raise ValueError(f"Run {ref} has no means (status={run.status})")
    rows = store.get_run_scores(ref)
    return RunSide(
        ref=ref,
        means={str(key): float(value) for key, value in run.means.items()},
        errors=run.error_count,
        abstained=run.abstained_count,
        row_count=len(rows),
        evaluator=run.evaluator,
        rows=rows,
    )


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def evaluator_mismatch(baseline: RunSide, head: RunSide) -> str | None:
    """Why the two sides cannot be gated against each other, or None.

    `stub` hashes, `lexical` overlap and `ragas` judge scores share metric names and
    nothing else, so a delta across evaluators is noise.
    """
    if not baseline.evaluator or not head.evaluator or baseline.evaluator == head.evaluator:
        return None
    return (
        f"Baseline was scored with the {baseline.evaluator!r} evaluator and head with "
        f"{head.evaluator!r}. Their scores are not comparable: score both with the same one."
    )


def compare_runs(
    baseline: RunSide, head: RunSide, *, threshold: float = DEFAULT_THRESHOLD
) -> RegressionReport:
    """The full gate: means, errored rows, abstained rows and question coverage."""
    missing_questions: int | None = None
    if baseline.rows is not None and head.rows is not None:
        missing_questions = sum(
            1 for _, right in pair_rows(baseline.rows, head.rows) if right is None
        )
    return compare_means(
        baseline.means,
        head.means,
        threshold=threshold,
        baseline_ref=baseline.ref,
        head_ref=head.ref,
        baseline_errors=baseline.errors,
        head_errors=head.errors,
        baseline_abstained=baseline.abstained,
        head_abstained=head.abstained,
        baseline_rows=baseline.row_count,
        head_rows=head.row_count,
        missing_questions=missing_questions,
    )


def require_rows(side: RunSide) -> list[RowScore]:
    if side.rows is None:
        raise ValueError(
            f"{side.ref} has no per-row scores; pass a run id or a snapshot from rag-eval eval -o"
        )
    return side.rows


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
