from __future__ import annotations

from pathlib import Path
from typing import Any

from rag_eval_harness.adapters.http import HttpAdapter
from rag_eval_harness.adapters.traces import TracesAdapter
from rag_eval_harness.evaluators import get_evaluator
from rag_eval_harness.io import RowCapError, load_path, load_text
from rag_eval_harness.store.models import Run
from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import ROW_CAP, EvalRow, MetricSummary


def _ensure_cap(rows: list[EvalRow]) -> list[EvalRow]:
    if len(rows) > ROW_CAP:
        raise RowCapError(f"Row cap is {ROW_CAP}; got {len(rows)} rows.")
    return rows


def execute_run(store: Store, run_id: str) -> Run:
    run = store.get_run(run_id)
    if run is None:
        raise KeyError(run_id)
    store.update_run(run_id, status="running")
    try:
        rows = store.get_dataset_rows(run.dataset_id)
        _ensure_cap(rows)
        config = run.adapter_config or {}
        if run.adapter_type == "http":
            url = config.get("url")
            if not url:
                raise ValueError("HTTP adapter requires adapter_config.url")
            rows = HttpAdapter(
                url,
                token=config.get("token"),
                timeout=float(config.get("timeout", 30)),
            ).run(rows)
        elif run.adapter_type == "traces":
            rows = TracesAdapter().run(rows)
        else:
            raise ValueError(f"Unknown adapter {run.adapter_type!r}")
        summary = get_evaluator(run.evaluator).evaluate(rows)
        return store.complete_run(run_id, summary)
    except Exception as exc:
        store.fail_run(run_id, str(exc))
        raise


def run_eval(
    store: Store,
    rows: list[EvalRow],
    *,
    dataset_name: str,
    filename: str | None = None,
    adapter_type: str,
    adapter_config: dict[str, Any] | None = None,
    evaluator: str = "stub",
    label: str | None = None,
    git_sha: str | None = None,
) -> tuple[Run, MetricSummary]:
    _ensure_cap(rows)
    # Re-running the same golden set lands on one dataset, so its runs share a
    # baseline tag instead of each run getting a dataset (and baseline) of its own.
    dataset = store.find_identical_dataset(rows, name=dataset_name) or store.create_dataset(
        rows, name=dataset_name, filename=filename
    )
    run = store.create_run(
        dataset_id=dataset.id,
        adapter_type=adapter_type,
        adapter_config=adapter_config or {},
        evaluator=evaluator,
        label=label,
        git_sha=git_sha,
        status="queued",
    )
    completed = execute_run(store, run.id)
    scores = store.get_run_scores(completed.id)
    summary = MetricSummary(
        means=completed.means or {},
        rows=scores,
        error_count=completed.error_count,
    )
    return completed, summary


def eval_from_path(
    store: Store,
    path: str | Path,
    *,
    sut_url: str | None = None,
    sut_token: str | None = None,
    timeout: float = 30.0,
    evaluator: str = "stub",
    label: str | None = None,
    git_sha: str | None = None,
) -> tuple[Run, MetricSummary]:
    file_path = Path(path)
    rows = load_path(file_path)
    if sut_url:
        adapter_type = "http"
        adapter_config: dict[str, Any] = {
            "url": sut_url,
            "timeout": timeout,
        }
        if sut_token:
            adapter_config["token"] = sut_token
    else:
        adapter_type = "traces"
        adapter_config = {"source": str(file_path)}
    return run_eval(
        store,
        rows,
        dataset_name=file_path.stem,
        filename=file_path.name,
        adapter_type=adapter_type,
        adapter_config=adapter_config,
        evaluator=evaluator,
        label=label,
        git_sha=git_sha,
    )


def eval_from_text(
    store: Store,
    text: str,
    *,
    filename: str,
    name: str | None = None,
    sut_url: str | None = None,
    sut_token: str | None = None,
    timeout: float = 30.0,
    evaluator: str = "stub",
    label: str | None = None,
    git_sha: str | None = None,
) -> tuple[Run, MetricSummary]:
    rows = load_text(text, filename=filename)
    adapter_type = "http" if sut_url else "traces"
    adapter_config: dict[str, Any] = {}
    if sut_url:
        adapter_config = {"url": sut_url, "timeout": timeout}
        if sut_token:
            adapter_config["token"] = sut_token
    return run_eval(
        store,
        rows,
        dataset_name=name or Path(filename).stem,
        filename=filename,
        adapter_type=adapter_type,
        adapter_config=adapter_config,
        evaluator=evaluator,
        label=label,
        git_sha=git_sha,
    )
