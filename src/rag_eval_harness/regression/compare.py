from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rag_eval_harness.store.repo import Store

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

    def failing(self) -> list[MetricDelta]:
        return [item for item in self.deltas if item.dropped]

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "threshold": self.threshold,
            "baseline_ref": self.baseline_ref,
            "head_ref": self.head_ref,
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
    passed = not any(item.dropped for item in deltas)
    return RegressionReport(
        passed=passed,
        threshold=threshold,
        baseline_ref=baseline_ref,
        head_ref=head_ref,
        deltas=deltas,
    )


def _means_from_payload(payload: dict[str, Any]) -> dict[str, float]:
    means = payload.get("means", payload)
    if not isinstance(means, dict):
        raise ValueError("Baseline/head JSON must contain a means object")
    return {str(key): float(value) for key, value in means.items() if key != "rows"}


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
