from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CreateRunRequest(BaseModel):
    dataset_id: str
    adapter: Literal["traces", "http"] = "traces"
    evaluator: Literal["stub", "lexical", "ragas"] = "stub"
    sut_url: str | None = None
    sut_token: str | None = None
    timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    label: str | None = None
    git_sha: str | None = None


class DatasetOut(BaseModel):
    id: str
    name: str
    filename: str | None
    row_count: int
    created_at: str


class RunOut(BaseModel):
    id: str
    dataset_id: str
    adapter_type: str
    adapter_config: dict[str, Any]
    evaluator: str
    label: str | None
    git_sha: str | None
    status: str
    error_message: str | None
    is_baseline: bool
    means: dict[str, float] | None
    error_count: int
    created_at: str
    completed_at: str | None


class RowScoreOut(BaseModel):
    question: str
    answer: str | None
    retrieved_contexts: list[str]
    ground_truth: str | None
    metrics: dict[str, float]
    error: str | None


class RunDetailOut(RunOut):
    rows: list[RowScoreOut]


class DiffOut(BaseModel):
    passed: bool
    threshold: float
    baseline: RunOut
    head: RunOut
    deltas: list[dict[str, Any]]
    rows: list[dict[str, Any]]
