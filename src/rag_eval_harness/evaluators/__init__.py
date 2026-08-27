from __future__ import annotations

from rag_eval_harness.evaluators.lexical import LexicalEvaluator
from rag_eval_harness.evaluators.protocol import Evaluator
from rag_eval_harness.evaluators.stub import StubEvaluator

__all__ = ["Evaluator", "LexicalEvaluator", "StubEvaluator", "get_evaluator"]


def get_evaluator(name: str) -> Evaluator:
    normalized = (name or "stub").strip().lower()
    if normalized == "stub":
        return StubEvaluator()
    if normalized == "lexical":
        return LexicalEvaluator()
    if normalized == "ragas":
        from rag_eval_harness.evaluators.ragas import RagasEvaluator

        return RagasEvaluator()
    raise ValueError(f"Unknown evaluator {name!r}. Use 'stub', 'lexical', or 'ragas'.")
