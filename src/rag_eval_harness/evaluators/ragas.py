from __future__ import annotations

import asyncio
import os
from collections.abc import Callable
from typing import Any

from rag_eval_harness.config import get_settings
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

METRIC_KWARGS: dict[str, tuple[str, ...]] = {
    METRIC_FAITHFULNESS: ("user_input", "response", "retrieved_contexts"),
    METRIC_ANSWER_RELEVANCY: ("user_input", "response"),
    METRIC_CONTEXT_PRECISION: ("user_input", "response", "retrieved_contexts", "reference"),
    METRIC_CONTEXT_RECALL: ("user_input", "response", "retrieved_contexts", "reference"),
}


class RagasUnavailableError(RuntimeError):
    pass


def _as_float(result: Any) -> float:
    if hasattr(result, "value"):
        value = result.value
    elif isinstance(result, dict) and "value" in result:
        value = result["value"]
    else:
        value = result
    number = float(value)
    return max(0.0, min(1.0, number))


async def _score_metric(metric: Any, **kwargs: Any) -> float:
    if hasattr(metric, "ascore"):
        result = metric.ascore(**kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return _as_float(result)
    if hasattr(metric, "score"):
        result = metric.score(**kwargs)
        if asyncio.iscoroutine(result):
            result = await result
        return _as_float(result)
    raise TypeError(f"Metric {metric!r} has neither ascore nor score")


def _default_metric_factory() -> dict[str, Any]:
    try:
        from openai import AsyncOpenAI
        from ragas.embeddings.base import embedding_factory
        from ragas.llms import llm_factory
        from ragas.metrics.collections import (
            AnswerRelevancy,
            ContextPrecision,
            ContextRecall,
            Faithfulness,
        )
    except ImportError as exc:
        raise RagasUnavailableError(
            "RAGAS extra is not installed. Run: pip install 'rag-eval-harness[ragas]'"
        ) from exc

    settings = get_settings()
    api_key = settings.openai_api_key or os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RagasUnavailableError(
            "OPENAI_API_KEY is required for the ragas evaluator "
            "(OpenAI-compatible endpoints are supported)."
        )
    client_kwargs: dict[str, Any] = {"api_key": api_key}
    if settings.openai_base_url:
        client_kwargs["base_url"] = settings.openai_base_url
    client = AsyncOpenAI(**client_kwargs)
    llm = llm_factory(settings.openai_model, client=client)
    embeddings = embedding_factory(
        "openai",
        model=settings.openai_embedding_model,
        client=client,
    )
    return {
        METRIC_FAITHFULNESS: Faithfulness(llm=llm),
        METRIC_ANSWER_RELEVANCY: AnswerRelevancy(llm=llm, embeddings=embeddings),
        METRIC_CONTEXT_PRECISION: ContextPrecision(llm=llm),
        METRIC_CONTEXT_RECALL: ContextRecall(llm=llm),
    }


class RagasEvaluator:
    """Wrap RAGAS collections metrics. Adaptive: context metrics only when ground_truth exists."""

    name = "ragas"

    def __init__(
        self,
        metrics: dict[str, Any] | None = None,
        metric_factory: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self._metrics = metrics
        self._metric_factory = metric_factory or _default_metric_factory

    def _get_metrics(self) -> dict[str, Any]:
        if self._metrics is None:
            self._metrics = self._metric_factory()
        return self._metrics

    async def _evaluate_row(self, row: EvalRow, metrics: dict[str, Any]) -> RowScore:
        if row.error:
            return RowScore(
                question=row.question,
                answer=row.answer,
                retrieved_contexts=row.retrieved_contexts,
                ground_truth=row.ground_truth,
                metrics={},
                error=row.error,
            )
        kwargs = {
            "user_input": row.question,
            "response": row.answer or "",
            "retrieved_contexts": row.retrieved_contexts,
        }
        if row.has_ground_truth():
            kwargs["reference"] = row.ground_truth
        scores: dict[str, float] = {}
        errors: list[str] = []
        wanted = [METRIC_FAITHFULNESS, METRIC_ANSWER_RELEVANCY]
        if row.has_ground_truth():
            wanted.extend([METRIC_CONTEXT_PRECISION, METRIC_CONTEXT_RECALL])
        for name in wanted:
            metric = metrics.get(name)
            if metric is None:
                continue
            allowed = METRIC_KWARGS.get(name, tuple(kwargs))
            call_kwargs = {key: value for key, value in kwargs.items() if key in allowed}
            try:
                scores[name] = await _score_metric(metric, **call_kwargs)
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {exc}")
        error = None if scores else ("; ".join(errors) or "ragas scoring failed")
        return RowScore(
            question=row.question,
            answer=row.answer,
            retrieved_contexts=row.retrieved_contexts,
            ground_truth=row.ground_truth,
            metrics=scores,
            error=error,
        )

    async def aevaluate(self, rows: list[EvalRow]) -> MetricSummary:
        metrics = self._get_metrics()
        scored = [await self._evaluate_row(row, metrics) for row in rows]
        return MetricSummary(
            means=compute_means(scored),
            rows=scored,
            error_count=sum(1 for row in scored if row.error),
        )

    def evaluate(self, rows: list[EvalRow]) -> MetricSummary:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.aevaluate(rows))
        # FastAPI / Jupyter already have a loop — isolate RAGAS on a fresh one.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=1) as pool:
            return pool.submit(lambda: asyncio.run(self.aevaluate(rows))).result()
