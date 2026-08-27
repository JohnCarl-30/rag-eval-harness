from __future__ import annotations

import re

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

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = frozenset(
    {
        "the",
        "and",
        "for",
        "are",
        "but",
        "not",
        "you",
        "all",
        "can",
        "our",
        "how",
        "what",
        "when",
        "does",
        "with",
        "from",
        "this",
        "that",
        "have",
        "has",
        "was",
        "into",
        "your",
        "about",
        "a",
        "an",
        "to",
        "of",
        "in",
        "on",
        "is",
        "or",
    }
)


def tokenize(text: str) -> set[str]:
    return {tok for tok in _TOKEN.findall(text.lower()) if tok not in _STOP and len(tok) > 1}


def overlap(numerator: set[str], denominator: set[str]) -> float:
    if not denominator:
        return 0.0
    return round(len(numerator & denominator) / len(denominator), 4)


class LexicalEvaluator:
    """Token overlap vs retrieved context. Keyless, sensitive to bad retrieval."""

    name = "lexical"

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
            answer_toks = tokenize(row.answer or "")
            question_toks = tokenize(row.question)
            context_toks = tokenize("\n".join(row.retrieved_contexts))
            metrics = {
                METRIC_FAITHFULNESS: overlap(context_toks, answer_toks),
                METRIC_ANSWER_RELEVANCY: overlap(answer_toks, question_toks),
            }
            if row.has_ground_truth():
                gt_toks = tokenize(row.ground_truth or "")
                metrics[METRIC_CONTEXT_PRECISION] = overlap(gt_toks, context_toks)
                metrics[METRIC_CONTEXT_RECALL] = overlap(context_toks, gt_toks)
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
