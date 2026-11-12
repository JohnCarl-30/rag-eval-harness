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
from rag_eval_harness.redact import redact_adapter_config, redact_error
from rag_eval_harness.regression.compare import (
    DEFAULT_THRESHOLD,
    RunSide,
    compare_runs,
    evaluator_mismatch,
    pair_rows,
)
from rag_eval_harness.regression.markdown import row_check_lines
from rag_eval_harness.store.models import Dataset, Run
from rag_eval_harness.store.repo import Store
from rag_eval_harness.types import RowScore

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
    return redact_adapter_config(config)


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
        error_message=redact_error(run.error_message, run.adapter_config),
        is_baseline=run.is_baseline,
        means=run.means,
        error_count=run.error_count,
        abstained_count=run.abstained_count,
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


def _run_job(store: Store, run_id: str, sut_url: str | None, sut_token: str | None) -> None:
    try:
        execute_run(store, run_id, sut_url=sut_url, sut_token=sut_token)
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
    # The store redacts the config, so the job carries the real URL and token itself.
    background_tasks.add_task(_run_job, store, run.id, payload.sut_url, payload.sut_token)
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
        rows=[
            RowScoreOut(
                question=row.question,
                answer=row.answer,
                retrieved_contexts=row.retrieved_contexts,
                ground_truth=row.ground_truth,
                metrics=row.metrics,
                error=redact_error(row.error, run.adapter_config),
                abstained=row.abstained,
            )
            for row in scores
        ],
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


def _run_side(run: Run, rows: list[RowScore]) -> RunSide:
    return RunSide(
        ref=run.id,
        means=run.means or {},
        errors=run.error_count,
        abstained=run.abstained_count,
        row_count=len(rows),
        evaluator=run.evaluator,
        rows=rows,
    )


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
    head_rows = store.get_run_scores(head.id)
    base_rows = store.get_run_scores(baseline.id)
    base_side = _run_side(baseline, base_rows)
    head_side = _run_side(head, head_rows)
    report = compare_runs(base_side, head_side, threshold=threshold)
    # Like `rag-eval diff`, this is for reading: two evaluators still line up, with a warning.
    mismatch = evaluator_mismatch(base_side, head_side)
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
        checks=[
            {"label": label, "baseline": left, "head": right, "failed": failed}
            for label, left, right, failed in row_check_lines(report)
        ],
        new_metrics=report.new_metrics,
        warnings=[mismatch] if mismatch else [],
        rows=paired,
    )
