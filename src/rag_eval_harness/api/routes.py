from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Query, Request, UploadFile

from rag_eval_harness.api.schemas import (
    CreateRunRequest,
    DatasetOut,
    DiffOut,
    RowScoreOut,
    RunDetailOut,
    RunOut,
)
from rag_eval_harness.engine import execute_run
from rag_eval_harness.io import LoadError, RowCapError, load_text
from rag_eval_harness.regression.compare import DEFAULT_THRESHOLD, compare_means, pair_rows
from rag_eval_harness.store.models import Dataset, Run
from rag_eval_harness.store.repo import Store

router = APIRouter(prefix="/api")


def _store(request: Request) -> Store:
    return request.app.state.store


def _iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _dataset_out(dataset: Dataset) -> DatasetOut:
    return DatasetOut(
        id=dataset.id,
        name=dataset.name,
        filename=dataset.filename,
        row_count=dataset.row_count,
        created_at=_iso(dataset.created_at) or "",
    )


def _redact(config: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(config or {})
    if data.get("token"):
        data["token"] = "***"
    return data


def _run_out(run: Run) -> RunOut:
    return RunOut(
        id=run.id,
        dataset_id=run.dataset_id,
        adapter_type=run.adapter_type,
        adapter_config=_redact(run.adapter_config),
        evaluator=run.evaluator,
        label=run.label,
        git_sha=run.git_sha,
        status=run.status,
        error_message=run.error_message,
        is_baseline=run.is_baseline,
        means=run.means,
        error_count=run.error_count,
        created_at=_iso(run.created_at) or "",
        completed_at=_iso(run.completed_at),
    )


@router.get("/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/auth")
def auth_status(request: Request) -> dict[str, bool]:
    return {"required": bool(request.app.state.auth_required)}


@router.post("/datasets", response_model=DatasetOut)
async def upload_dataset(
    request: Request,
    file: UploadFile = File(...),
    name: str | None = None,
) -> DatasetOut:
    store = _store(request)
    raw = await file.read()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="File must be UTF-8 text") from exc
    filename = file.filename or "upload.csv"
    try:
        rows = load_text(text, filename=filename)
    except (LoadError, RowCapError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dataset = store.create_dataset(rows, name=name or Path(filename).stem, filename=filename)
    return _dataset_out(dataset)


@router.get("/datasets", response_model=list[DatasetOut])
def list_datasets(request: Request) -> list[DatasetOut]:
    return [_dataset_out(item) for item in _store(request).list_datasets()]


@router.get("/datasets/{dataset_id}", response_model=DatasetOut)
def get_dataset(dataset_id: str, request: Request) -> DatasetOut:
    dataset = _store(request).get_dataset(dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _dataset_out(dataset)


@router.get("/datasets/{dataset_id}/rows")
def dataset_rows(dataset_id: str, request: Request) -> list[dict[str, Any]]:
    store = _store(request)
    if store.get_dataset(dataset_id) is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    rows = store.get_dataset_rows(dataset_id)
    return [
        {
            "question": row.question,
            "ground_truth": row.ground_truth,
            "answer": row.answer,
            "retrieved_contexts": row.retrieved_contexts,
        }
        for row in rows
    ]


def _run_job(store: Store, run_id: str) -> None:
    try:
        execute_run(store, run_id)
    except Exception:
        # execute_run already marks the run failed
        return


@router.post("/runs", response_model=RunOut)
def create_run(
    payload: CreateRunRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> RunOut:
    store = _store(request)
    dataset = store.get_dataset(payload.dataset_id)
    if dataset is None:
        raise HTTPException(status_code=404, detail="Dataset not found")
    if payload.adapter == "http" and not payload.sut_url:
        raise HTTPException(status_code=400, detail="sut_url is required for the HTTP adapter")
    config: dict[str, Any] = {}
    if payload.adapter == "http":
        config = {"url": payload.sut_url, "timeout": payload.timeout_seconds}
        if payload.sut_token:
            config["token"] = payload.sut_token
    run = store.create_run(
        dataset_id=payload.dataset_id,
        adapter_type=payload.adapter,
        adapter_config=config,
        evaluator=payload.evaluator,
        label=payload.label,
        git_sha=payload.git_sha,
        status="queued",
    )
    background_tasks.add_task(_run_job, store, run.id)
    return _run_out(run)


@router.get("/runs", response_model=list[RunOut])
def list_runs(request: Request, dataset_id: str | None = None) -> list[RunOut]:
    return [_run_out(run) for run in _store(request).list_runs(dataset_id)]


@router.get("/runs/{run_id}", response_model=RunDetailOut)
def get_run(run_id: str, request: Request) -> RunDetailOut:
    store = _store(request)
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    scores = store.get_run_scores(run_id)
    base = _run_out(run)
    return RunDetailOut(
        **base.model_dump(),
        rows=[RowScoreOut(**row.to_dict()) for row in scores],
    )


@router.post("/runs/{run_id}/baseline", response_model=RunOut)
def set_baseline(run_id: str, request: Request) -> RunOut:
    store = _store(request)
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status != "completed":
        raise HTTPException(
            status_code=409, detail=f"Only a completed run can be a baseline (status={run.status})"
        )
    return _run_out(store.set_baseline(run_id))


@router.get("/runs/{run_id}/diff", response_model=DiffOut)
def diff_runs(
    run_id: str,
    request: Request,
    against: str,
    threshold: float = Query(default=DEFAULT_THRESHOLD),
) -> DiffOut:
    store = _store(request)
    head = store.get_run(run_id)
    baseline = store.get_run(against)
    if head is None or baseline is None:
        raise HTTPException(status_code=404, detail="Run not found")
    report = compare_means(
        baseline.means or {},
        head.means or {},
        threshold=threshold,
        baseline_ref=baseline.id,
        head_ref=head.id,
        baseline_errors=baseline.error_count,
        head_errors=head.error_count,
    )
    head_rows = store.get_run_scores(head.id)
    base_rows = store.get_run_scores(baseline.id)
    paired = [
        {
            "index": index,
            "question": (right or left).question,
            "baseline": None if left is None else left.to_dict(),
            "head": None if right is None else right.to_dict(),
        }
        for index, (left, right) in enumerate(pair_rows(base_rows, head_rows))
        if left is not None or right is not None
    ]
    return DiffOut(
        passed=report.passed,
        threshold=report.threshold,
        baseline=_run_out(baseline),
        head=_run_out(head),
        deltas=report.to_dict()["deltas"],
        rows=paired,
    )
