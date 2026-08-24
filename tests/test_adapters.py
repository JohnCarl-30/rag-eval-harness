from __future__ import annotations

import httpx

from rag_eval_harness.adapters.http import HttpAdapter
from rag_eval_harness.adapters.traces import TracesAdapter
from rag_eval_harness.types import EvalRow


def test_traces_marks_missing_answers() -> None:
    rows = [
        EvalRow(question="Q", answer="A"),
        EvalRow(question="Missing"),
    ]
    out = TracesAdapter().run(rows)
    assert out[0].error is None
    assert out[1].error == "missing answer for traces adapter"


def test_http_adapter_success_and_row_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = request.read()
        if b"boom" in payload:
            return httpx.Response(500, json={"detail": "nope"})
        return httpx.Response(
            200,
            json={"answer": "ok", "retrieved_contexts": ["ctx"]},
        )

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    adapter = HttpAdapter("https://rag.example/query", token="secret", client=client)
    rows = [
        EvalRow(question="hello", ground_truth="gt"),
        EvalRow(question="boom"),
    ]
    out = adapter.run(rows)
    assert out[0].answer == "ok"
    assert out[0].retrieved_contexts == ["ctx"]
    assert out[0].ground_truth == "gt"
    assert out[1].error is not None
    assert "500" in out[1].error or "http adapter" in out[1].error


def test_http_adapter_sends_bearer(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["authorization"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"response": "alias", "contexts": "one|two"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = HttpAdapter("https://rag.example/query", token="abc", client=client).run(
        [EvalRow(question="q")]
    )
    assert seen["authorization"] == "Bearer abc"
    assert out[0].answer == "alias"
    assert out[0].retrieved_contexts == ["one", "two"]
