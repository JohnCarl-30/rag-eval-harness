from __future__ import annotations

from rag_eval_harness.evaluators.tokens import tokenize
from rag_eval_harness.types import METRIC_MRR, METRIC_RECALL_AT_K, EvalRow

# Without labels, a passage counts as relevant when it holds at least this share of the
# ground-truth tokens. It is a proxy: label reference_contexts for exact Recall@k.
GROUND_TRUTH_COVERAGE = 0.5


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def _label_hits(contexts: list[str], references: list[str]) -> tuple[int, int | None]:
    """How many references appear in the contexts, and the 1-based rank of the first match."""
    normalized = [_normalize(context) for context in contexts]
    found = 0
    first_rank: int | None = None
    for reference in references:
        needle = _normalize(reference)
        ranks = [rank for rank, context in enumerate(normalized, 1) if needle in context]
        if ranks:
            found += 1
            first_rank = ranks[0] if first_rank is None else min(first_rank, ranks[0])
    return found, first_rank


def _ground_truth_rank(contexts: list[str], ground_truth: str) -> int | None:
    wanted = tokenize(ground_truth)
    if not wanted:
        return None
    for rank, context in enumerate(contexts, 1):
        if len(wanted & tokenize(context)) / len(wanted) >= GROUND_TRUTH_COVERAGE:
            return rank
    return None


def retrieval_metrics(row: EvalRow) -> dict[str, float]:
    """recall_at_k and mrr over the retrieved contexts, with k = however many came back.

    With reference_contexts, recall is the share of references found. Without them, a row
    with ground truth has one implied relevant passage, so recall is a hit (1.0) or a miss.
    A row with neither gets no retrieval metrics.
    """
    references = [ref for ref in row.reference_contexts if ref.strip()]
    if references:
        found, first_rank = _label_hits(row.retrieved_contexts, references)
        recall = found / len(references)
    elif row.has_ground_truth():
        first_rank = _ground_truth_rank(row.retrieved_contexts, row.ground_truth or "")
        recall = 0.0 if first_rank is None else 1.0
    else:
        return {}
    return {
        METRIC_RECALL_AT_K: round(recall, 4),
        METRIC_MRR: 0.0 if first_rank is None else round(1 / first_rank, 4),
    }
