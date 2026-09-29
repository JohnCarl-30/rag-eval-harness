from __future__ import annotations

from typing import Any

import httpx

from rag_eval_harness.io import parse_contexts
from rag_eval_harness.types import EvalRow, is_truthy


def _row_error(exc: BaseException) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "http adapter: timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        return f"http adapter: HTTP {exc.response.status_code}"
    return f"http adapter: {type(exc).__name__}"


class HttpAdapter:
    """POST {\"question\"} to a user RAG endpoint and collect answer + contexts."""

    name = "http"

    def __init__(
        self,
        url: str,
        *,
        token: str | None = None,
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self.url = url
        self.token = token
        self.timeout = timeout
        self._client = client

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _parse_response(self, payload: Any) -> tuple[str | None, list[str], bool]:
        if not isinstance(payload, dict):
            raise ValueError("SUT response must be a JSON object")
        answer = payload.get("answer", payload.get("response"))
        contexts = payload.get("retrieved_contexts", payload.get("contexts"))
        abstained = payload.get("abstained", payload.get("escalated"))
        if answer is None or not str(answer).strip():
            raise ValueError("SUT response missing answer")
        return str(answer), parse_contexts(contexts), is_truthy(abstained)

    def run(self, rows: list[EvalRow]) -> list[EvalRow]:
        owns_client = self._client is None
        client = self._client or httpx.Client(timeout=self.timeout)
        try:
            out: list[EvalRow] = []
            for row in rows:
                if row.error:
                    out.append(row)
                    continue
                try:
                    response = client.post(
                        self.url,
                        json={"question": row.question},
                        headers=self._headers(),
                    )
                    response.raise_for_status()
                    answer, contexts, abstained = self._parse_response(response.json())
                    out.append(
                        EvalRow(
                            question=row.question,
                            answer=answer,
                            retrieved_contexts=contexts,
                            ground_truth=row.ground_truth,
                            abstained=abstained,
                            reference_contexts=row.reference_contexts,
                        )
                    )
                except Exception as exc:  # noqa: BLE001 — per-row failure must not abort the run
                    out.append(
                        EvalRow(
                            question=row.question,
                            answer=row.answer,
                            retrieved_contexts=row.retrieved_contexts,
                            ground_truth=row.ground_truth,
                            error=_row_error(exc),
                            reference_contexts=row.reference_contexts,
                        )
                    )
            return out
        finally:
            if owns_client:
                client.close()
