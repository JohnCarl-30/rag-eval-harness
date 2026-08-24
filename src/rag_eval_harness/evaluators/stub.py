from __future__ import annotations

import hashlib

from rag_eval_harness.types import (
    METRIC_ANSWER_RELEVANCY,
    METRIC_CONTEXT_PRECISION,
    METRIC_CONTEXT_RECALL,
    METRIC_FAITHFULNESS,
    EvalRow,
    MetricSummary,
    RowScore,
    compute_means,
)


def _stable_unit(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    integer = int(digest[:8], 16)
    return round(0.5 + (integer / 0xFFFFFFFF) * 0.5, 4)


class StubEvaluator:
    """Deterministic, keyless scores so UI and CI work without a judge."""

    name = "stub"

    def evaluate(self, rows: list[EvalRow]) -> MetricSummary:
        scored: list[RowScore] = []
        for row in rows:
            if row.error:
                scored.append(
                    RowScore(
                        question=row.question,
                        answer=row.answer,
                        retrieved_contexts=row.retrieved_contexts,
                        ground_truth=row.ground_truth,
                        metrics={},
                        error=row.error,
                    )
                )
                continue
            answer = row.answer or ""
            joined_contexts = "\n".join(row.retrieved_contexts)
            metrics = {
                METRIC_FAITHFULNESS: _stable_unit(f"faith|{answer}|{joined_contexts}"),
                METRIC_ANSWER_RELEVANCY: _stable_unit(f"rel|{row.question}|{answer}"),
            }
            if row.has_ground_truth():
                gt = row.ground_truth or ""
                metrics[METRIC_CONTEXT_PRECISION] = _stable_unit(f"prec|{gt}|{joined_contexts}")
                metrics[METRIC_CONTEXT_RECALL] = _stable_unit(f"rec|{gt}|{joined_contexts}")
            scored.append(
                RowScore(
                    question=row.question,
                    answer=row.answer,
                    retrieved_contexts=row.retrieved_contexts,
                    ground_truth=row.ground_truth,
                    metrics=metrics,
                )
            )
        return MetricSummary(
            means=compute_means(scored),
            rows=scored,
            error_count=sum(1 for row in scored if row.error),
        )
