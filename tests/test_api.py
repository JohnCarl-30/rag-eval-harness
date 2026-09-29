from __future__ import annotations

from fastapi.testclient import TestClient

from rag_eval_harness.api.app import create_app
from rag_eval_harness.store.repo import Store


def test_loopback_open_and_run_lifecycle(store: Store, traces_jsonl) -> None:
    app = create_app(store, bind_host="127.0.0.1", api_key=None)
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    assert client.get("/api/auth").json()["required"] is False

    upload = client.post(
        "/api/datasets",
        files={"file": ("traces.jsonl", traces_jsonl.read_bytes(), "application/jsonl")},
    )
    assert upload.status_code == 200, upload.text
    dataset_id = upload.json()["id"]
    assert upload.json()["row_count"] == 16

    created = client.post(
        "/api/runs",
        json={"dataset_id": dataset_id, "adapter": "traces", "evaluator": "stub", "label": "ui"},
    )
    assert created.status_code == 200
    run_id = created.json()["id"]

    detail = client.get(f"/api/runs/{run_id}")
    # BackgroundTasks run after the response in TestClient
    detail = client.get(f"/api/runs/{run_id}")
    assert detail.json()["status"] in {"completed", "running", "queued"}
    # Force a follow-up poll; TestClient executes background tasks before returning
    assert detail.json()["status"] == "completed"
    assert "faithfulness" in (detail.json()["means"] or {})
    assert len(detail.json()["rows"]) == 16

    tagged = client.post(f"/api/runs/{run_id}/baseline")
    assert tagged.json()["is_baseline"] is True

    other = client.post(
        "/api/runs",
        json={"dataset_id": dataset_id, "adapter": "traces", "evaluator": "lexical"},
    )
    assert other.status_code == 200, other.text
    assert other.json()["evaluator"] == "lexical"
    diff = client.get(f"/api/runs/{other.json()['id']}/diff", params={"against": run_id})
    assert diff.status_code == 200
    assert "deltas" in diff.json()
    assert "rows" in diff.json()


def test_non_loopback_requires_api_key(store: Store) -> None:
    app = create_app(store, bind_host="0.0.0.0", api_key="secret")
    client = TestClient(app)
    assert client.get("/health").status_code == 200
    assert client.get("/api/auth").json()["required"] is True
    assert client.get("/api/datasets").status_code == 401
    ok = client.get("/api/datasets", headers={"X-API-Key": "secret"})
    assert ok.status_code == 200
    bearer = client.get("/api/datasets", headers={"Authorization": "Bearer secret"})
    assert bearer.status_code == 200
    bad = client.get("/api/datasets", headers={"X-API-Key": "nope"})
    assert bad.status_code == 401


def test_http_run_with_dummy_handler(store: Store, golden_csv) -> None:
    import httpx

    from rag_eval_harness.adapters.http import HttpAdapter
    from rag_eval_harness.engine import eval_from_path
    from rag_eval_harness.io import load_path

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"answer": "canned", "retrieved_contexts": ["ctx"]})

    rows = load_path(golden_csv)
    client = httpx.Client(transport=httpx.MockTransport(handler))
    out = HttpAdapter("https://dummy/query", client=client).run(rows)
    assert all(row.answer == "canned" for row in out)

    run, summary = eval_from_path(store, golden_csv, evaluator="stub")
    # golden csv has no answers → traces adapter should record row errors
    assert run.status == "completed"
    assert summary.error_count == 16


def test_api_redacts_http_adapter_secrets(store: Store, golden_csv) -> None:
    app = create_app(store, bind_host="127.0.0.1", api_key=None)
    client = TestClient(app)
    upload = client.post(
        "/api/datasets",
        files={"file": ("golden.csv", golden_csv.read_bytes(), "text/csv")},
    )
    assert upload.status_code == 200, upload.text
    created = client.post(
        "/api/runs",
        json={
            "dataset_id": upload.json()["id"],
            "adapter": "http",
            "sut_url": "https://rag.example/eval?api_key=SUPERSECRET",
            "sut_token": "tok_live_xyz",
            "timeout_seconds": 0.2,
            "evaluator": "stub",
        },
    )
    assert created.status_code == 200, created.text
    assert "SUPERSECRET" not in created.text
    assert "tok_live_xyz" not in created.text
    config = created.json()["adapter_config"]
    assert config["token"] == "***"
    assert config["url"] == "https://rag.example/eval"

    detail = client.get(f"/api/runs/{created.json()['id']}")
    assert "SUPERSECRET" not in detail.text
    assert "tok_live_xyz" not in detail.text
    assert detail.json()["adapter_config"]["token"] == "***"
    assert detail.json()["adapter_config"]["url"] == "https://rag.example/eval"


def test_spa_route_does_not_serve_files_outside_dist(store: Store, tmp_path, monkeypatch) -> None:
    dist = tmp_path / "web" / "dist"
    dist.mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>", encoding="utf-8")
    (dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("SECRET", encoding="utf-8")
    monkeypatch.setattr("rag_eval_harness.api.app.find_web_dist", lambda: dist)
    client = TestClient(create_app(store, bind_host="0.0.0.0", api_key="secret"))

    assert client.get("/favicon.svg").text == "<svg/>"
    for path in ("/..%2f..%2fsecret.txt", "/%2e%2e/%2e%2e/secret.txt", "/..%2fdist2"):
        response = client.get(path)
        assert "SECRET" not in response.text, path
        assert response.text == "<html>spa</html>", path


def test_cross_origin_reads_are_off_by_default(store: Store, monkeypatch) -> None:
    monkeypatch.delenv("RAG_EVAL_CORS_ORIGINS", raising=False)
    client = TestClient(create_app(store, bind_host="127.0.0.1", api_key=None))
    response = client.get("/api/datasets", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in response.headers

    # A no-preflight text/plain POST must not be parsed as a run request.
    blind = client.post(
        "/api/runs",
        content='{"dataset_id":"x","adapter":"http","sut_url":"http://10.0.0.1/"}',
        headers={"Origin": "https://evil.example", "Content-Type": "text/plain"},
    )
    assert blind.status_code == 422


def test_cors_origins_are_opt_in(store: Store, monkeypatch) -> None:
    monkeypatch.setenv("RAG_EVAL_CORS_ORIGINS", "https://dash.example, https://other.example")
    client = TestClient(create_app(store, bind_host="127.0.0.1", api_key=None))
    allowed = client.get("/api/datasets", headers={"Origin": "https://dash.example"})
    assert allowed.headers["access-control-allow-origin"] == "https://dash.example"
    denied = client.get("/api/datasets", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in denied.headers


def test_diff_fails_when_head_errors_more(store: Store) -> None:
    from rag_eval_harness.types import EvalRow, MetricSummary, RowScore

    dataset = store.create_dataset([EvalRow(question="Q", answer="A")] * 2, name="d")
    ok = RowScore("Q", "A", [], None, {"faithfulness": 0.8})
    bad = RowScore("Q", "A", [], None, {}, error="http adapter: timeout")
    ids = []
    for rows in ([ok, ok], [ok, bad]):
        run = store.create_run(dataset_id=dataset.id, adapter_type="traces", evaluator="stub")
        errors = sum(1 for row in rows if row.error)
        store.complete_run(
            run.id, MetricSummary(means={"faithfulness": 0.8}, rows=rows, error_count=errors)
        )
        ids.append(run.id)
    client = TestClient(create_app(store, bind_host="127.0.0.1", api_key=None))
    diff = client.get(f"/api/runs/{ids[1]}/diff", params={"against": ids[0]}).json()
    assert diff["passed"] is False
    assert all(not item["dropped"] for item in diff["deltas"])


def test_upload_names_dataset_by_stem_and_rejects_empty(store: Store, traces_jsonl) -> None:
    client = TestClient(create_app(store, bind_host="127.0.0.1", api_key=None))
    upload = client.post(
        "/api/datasets",
        files={"file": ("traces.jsonl", traces_jsonl.read_bytes(), "application/jsonl")},
    )
    assert upload.json()["name"] == "traces"
    assert upload.json()["filename"] == "traces.jsonl"
    empty = client.post("/api/datasets", files={"file": ("notes.txt", b"", "text/plain")})
    assert empty.status_code == 400


def test_baseline_requires_completed_run_and_diff_pairs_by_question(store: Store) -> None:
    from rag_eval_harness.types import EvalRow, MetricSummary, RowScore

    dataset = store.create_dataset([EvalRow(question="Q", answer="A")], name="d")
    client = TestClient(create_app(store, bind_host="127.0.0.1", api_key=None))
    pending = store.create_run(dataset_id=dataset.id, adapter_type="traces", evaluator="stub")
    assert client.post(f"/api/runs/{pending.id}/baseline").status_code == 409

    ids = []
    for rows in (
        [RowScore("a", "x", [], None, {"faithfulness": 0.9}), RowScore("b", "x", [], None, {})],
        [RowScore("b", "x", [], None, {}), RowScore("a", "x", [], None, {"faithfulness": 0.9})],
    ):
        run = store.create_run(dataset_id=dataset.id, adapter_type="traces", evaluator="stub")
        store.complete_run(run.id, MetricSummary(means={}, rows=rows, error_count=0))
        ids.append(run.id)
    assert client.post(f"/api/runs/{ids[0]}/baseline").status_code == 200
    diff = client.get(f"/api/runs/{ids[1]}/diff", params={"against": ids[0]}).json()
    assert [(row["baseline"]["question"], row["head"]["question"]) for row in diff["rows"]] == [
        ("b", "b"),
        ("a", "a"),
    ]
