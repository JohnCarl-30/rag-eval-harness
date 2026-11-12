"""SUT credentials stay in memory, and a configured API key is always enforced."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from rag_eval_harness import engine as engine_mod
from rag_eval_harness.api.app import create_app
from rag_eval_harness.cli import app
from rag_eval_harness.engine import execute_run
from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import EvalRow

runner = CliRunner()

SUT_URL = "https://user:pw_SECRET@rag.example/eval?api_key=QUERY_SECRET"
SUT_TOKEN = "tok_live_SECRET"
SECRETS = ("pw_SECRET", "QUERY_SECRET", SUT_TOKEN)


def _db_path(store: Store) -> Path:
    return Path(store.url.removeprefix("sqlite:///"))


def _stored_configs(path: Path) -> str:
    with sqlite3.connect(path) as connection:
        rows = connection.execute("select adapter_config, error_message from runs").fetchall()
    return json.dumps(rows)


@pytest.fixture
def seen(monkeypatch) -> dict:
    """Replace the HTTP adapter with one that records what it was given."""
    calls: dict = {}

    class FakeHttp:
        def __init__(self, url, *, token=None, timeout=30.0):
            calls.update(url=url, token=token)

        def run(self, rows):
            if calls.get("explode"):
                raise RuntimeError(f"boom calling {calls['url']} with {calls['token']}")
            return [
                EvalRow(question=row.question, answer="canned", retrieved_contexts=["ctx"])
                for row in rows
            ]

    monkeypatch.setattr(engine_mod, "HttpAdapter", FakeHttp)
    return calls


def test_cli_eval_keeps_sut_secrets_out_of_the_database(tmp_path, golden_csv, seen) -> None:
    db = tmp_path / "cli.db"
    result = runner.invoke(
        app,
        [
            "eval",
            str(golden_csv),
            "--sut-url",
            SUT_URL,
            "--sut-token",
            SUT_TOKEN,
            "--db",
            f"sqlite:///{db}",
        ],
    )

    assert result.exit_code == 0, result.output
    # The adapter still got the real URL and token.
    assert seen == {"url": SUT_URL, "token": SUT_TOKEN}
    stored = _stored_configs(db)
    assert "rag.example/eval" in stored
    for secret in SECRETS:
        assert secret not in stored
        assert secret not in result.output


def test_sut_token_can_come_from_the_environment(tmp_path, golden_csv, seen, monkeypatch) -> None:
    monkeypatch.setenv("RAG_EVAL_SUT_TOKEN", SUT_TOKEN)
    result = runner.invoke(
        app,
        [
            "eval",
            str(golden_csv),
            "--sut-url",
            "https://rag.example/eval",
            "--db",
            f"sqlite:///{tmp_path / 'cli.db'}",
        ],
    )

    assert result.exit_code == 0, result.output
    assert seen["token"] == SUT_TOKEN


def test_api_run_uses_the_token_without_storing_it(store: Store, golden_csv, seen) -> None:
    client = TestClient(create_app(store, bind_host="127.0.0.1", api_key=""))
    upload = client.post(
        "/api/datasets", files={"file": ("golden.csv", golden_csv.read_bytes(), "text/csv")}
    )
    created = client.post(
        "/api/runs",
        json={
            "dataset_id": upload.json()["id"],
            "adapter": "http",
            "sut_url": SUT_URL,
            "sut_token": SUT_TOKEN,
            "evaluator": "stub",
        },
    )

    assert created.status_code == 200, created.text
    assert seen == {"url": SUT_URL, "token": SUT_TOKEN}
    detail = client.get(f"/api/runs/{created.json()['id']}").json()
    assert detail["status"] == "completed"
    assert detail["error_count"] == 0
    stored = _stored_configs(_db_path(store))
    for secret in SECRETS:
        assert secret not in stored


def test_failed_run_message_does_not_keep_the_secrets(store: Store, seen) -> None:
    seen["explode"] = True
    dataset = store.create_dataset([EvalRow(question="Q")], name="d")
    run = store.create_run(
        dataset_id=dataset.id,
        adapter_type="http",
        adapter_config={"url": SUT_URL, "token": SUT_TOKEN},
        evaluator="stub",
    )

    with pytest.raises(RuntimeError):
        execute_run(store, run.id, sut_url=SUT_URL, sut_token=SUT_TOKEN)

    failed = store.get_run(run.id)
    assert failed.status == "failed"
    assert "boom calling" in failed.error_message
    stored = _stored_configs(_db_path(store))
    for secret in SECRETS:
        assert secret not in stored


def test_http_run_needs_its_url_from_the_caller(store: Store) -> None:
    dataset = store.create_dataset([EvalRow(question="Q")], name="d")
    run = store.create_run(
        dataset_id=dataset.id,
        adapter_type="http",
        adapter_config={"url": "https://rag.example/eval?variant=chunked"},
        evaluator="stub",
    )

    # The stored URL has lost its query, so calling it would test the wrong variant.
    with pytest.raises(ValueError, match="sut_url"):
        execute_run(store, run.id)
    assert store.get_run(run.id).status == "failed"


def test_store_scrubs_secrets_written_by_older_versions(store: Store) -> None:
    dataset = store.create_dataset([EvalRow(question="Q", answer="A")], name="d")
    run = store.create_run(dataset_id=dataset.id, adapter_type="http", evaluator="stub")
    path = _db_path(store)
    old_config = json.dumps({"url": SUT_URL, "token": SUT_TOKEN, "timeout": 30})
    with sqlite3.connect(path) as connection:
        connection.execute("update runs set adapter_config = ? where id = ?", (old_config, run.id))
    assert SUT_TOKEN in _stored_configs(path)

    reopened = Store(store.url)

    stored = _stored_configs(path)
    for secret in SECRETS:
        assert secret not in stored
    config = reopened.get_run(run.id).adapter_config
    assert config == {"url": "https://***@rag.example/eval", "token": "***", "timeout": 30}
    # Opening again changes nothing.
    assert Store(store.url).get_run(run.id).adapter_config == config


def test_api_key_is_enforced_on_loopback_when_set(store: Store) -> None:
    client = TestClient(create_app(store, bind_host="127.0.0.1", api_key="secret"))

    assert client.get("/api/auth").json()["required"] is True
    assert client.get("/health").status_code == 200
    assert client.get("/api/runs").status_code == 401
    assert client.get("/api/runs", headers={"X-API-Key": "nope"}).status_code == 401
    assert client.get("/api/runs", headers={"X-API-Key": "secret"}).status_code == 200


def test_loopback_without_a_key_stays_open(store: Store) -> None:
    client = TestClient(create_app(store, bind_host="127.0.0.1", api_key=""))

    assert client.get("/api/auth").json()["required"] is False
    assert client.get("/api/runs").status_code == 200
