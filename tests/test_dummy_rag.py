from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx

from rag_eval_harness.adapters.http import HttpAdapter
from rag_eval_harness.types import EvalRow

SERVER = Path(__file__).resolve().parents[1] / "examples" / "dummy-rag" / "server.py"


def _load_server():
    spec = importlib.util.spec_from_file_location("dummy_rag_server", SERVER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dummy_retrieve_office_hours() -> None:
    module = _load_server()
    answer, contexts = module.retrieve("What are the Acme Docs office hours?")
    assert "09:00" in answer
    assert contexts


def test_dummy_retrieve_spanish_support() -> None:
    module = _load_server()
    answer, contexts = module.retrieve("¿Cómo contacto a soporte?")
    assert "docs-help" in answer
    assert "Soporte" in contexts[0]


def test_dummy_http_adapter_roundtrip() -> None:
    module = _load_server()

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.read().decode() or "{}")
        answer, contexts = module.retrieve(str(body.get("question") or ""))
        return httpx.Response(200, json={"answer": answer, "retrieved_contexts": contexts})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = HttpAdapter("https://dummy/query", client=client).run(
        [EvalRow(question="What is the API rate limit?", ground_truth="60 req/min")]
    )
    assert out[0].error is None
    assert "60" in (out[0].answer or "")
