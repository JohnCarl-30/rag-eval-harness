from __future__ import annotations

from typing import Protocol, runtime_checkable

from rag_eval_harness.types import EvalRow, MetricSummary


@runtime_checkable
class Evaluator(Protocol):
    name: str

    def evaluate(self, rows: list[EvalRow]) -> MetricSummary: ...
