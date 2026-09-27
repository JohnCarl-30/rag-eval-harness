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
    assert out[1].error == "http adapter: HTTP 500"


def test_http_adapter_row_error_omits_url() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "nope"})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    url = "https://rag.example/query?api_key=SUPERSECRET"
    out = HttpAdapter(url, timeout=1.0, client=client).run([EvalRow(question="q")])
    assert out[0].error == "http adapter: HTTP 500"
    assert "SUPERSECRET" not in (out[0].error or "")
    assert "rag.example" not in (out[0].error or "")


def test_http_adapter_timeout() -> None:
    import threading
    import time
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Slow(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            time.sleep(1.0)
            self.send_response(200)
            self.end_headers()

        def log_message(self, format: str, *args: object) -> None:  # noqa: A002
            return

    server = HTTPServer(("127.0.0.1", 0), Slow)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/query"
        out = HttpAdapter(url, timeout=0.2).run([EvalRow(question="q")])
        assert out[0].error == "http adapter: timeout"
        assert "127.0.0.1" not in (out[0].error or "")
    finally:
        server.shutdown()


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


def test_http_adapter_rejects_blank_answer() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": "  ", "retrieved_contexts": ["ctx"]})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = HttpAdapter("https://rag.example/query", client=client).run([EvalRow(question="q")])

    assert out[0].error == "http adapter: ValueError"
