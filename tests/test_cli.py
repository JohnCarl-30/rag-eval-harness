from __future__ import annotations

import json

from typer.testing import CliRunner

from rag_eval_harness.cli import app
from rag_eval_harness.engine import eval_from_path

runner = CliRunner()


def test_eval_traces_cli(tmp_path, traces_jsonl) -> None:
    db = tmp_path / "cli.db"
    result = runner.invoke(
        app,
        ["eval", str(traces_jsonl), "--evaluator", "stub", "--db", f"sqlite:///{db}"],
    )
    assert result.exit_code == 0, result.output
    assert "Run id:" in result.output
    assert "faithfulness" in result.output


def test_eval_rejects_over_cap(tmp_path) -> None:
    path = tmp_path / "too-big.csv"
    path.write_text("question\n" + "\n".join(f"q{i}" for i in range(101)), encoding="utf-8")
    result = runner.invoke(app, ["eval", str(path), "--db", f"sqlite:///{tmp_path / 'x.db'}"])
    assert result.exit_code == 2
    assert "Row cap" in result.output


def test_baseline_and_regress_exit_codes(tmp_path, traces_jsonl, store) -> None:
    db_url = store.url
    run, _ = eval_from_path(store, traces_jsonl, evaluator="stub", label="base")
    tagged = runner.invoke(app, ["baseline", run.id, "--db", db_url])
    assert tagged.exit_code == 0

    good = tmp_path / "good.json"
    good.write_text(json.dumps({"means": run.means}), encoding="utf-8")
    ok = runner.invoke(
        app,
        [
            "regress",
            "--baseline",
            str(good),
            "--head",
            run.id,
            "--threshold",
            "0.05",
            "--db",
            db_url,
        ],
    )
    assert ok.exit_code == 0, ok.output

    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"means": {name: max(0.0, value - 0.2) for name, value in run.means.items()}}),
        encoding="utf-8",
    )
    # Compare a worse "head" file against the stored baseline run
    failed = runner.invoke(
        app,
        [
            "regress",
            "--baseline",
            run.id,
            "--head",
            str(bad),
            "--threshold",
            "0.05",
            "--db",
            db_url,
        ],
    )
    assert failed.exit_code == 1, failed.output
    assert "Regression detected" in failed.output


def test_version() -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert result.output.strip()


def test_serve_requires_key_off_loopback(monkeypatch) -> None:
    monkeypatch.delenv("RAG_EVAL_API_KEY", raising=False)
    from rag_eval_harness.config import clear_settings_cache

    clear_settings_cache()
    result = runner.invoke(app, ["serve", "--host", "0.0.0.0", "--port", "8000"])
    assert result.exit_code == 1
    assert "RAG_EVAL_API_KEY" in result.output