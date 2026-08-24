from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, selectinload, sessionmaker

from rag_eval_harness.store.models import Base, Dataset, DatasetRow, Run, RunScore
from rag_eval_harness.types import EvalRow, MetricSummary, RowScore


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _new_id() -> str:
    return str(uuid.uuid4())


def make_engine(url: str) -> Engine:
    connect_args: dict[str, Any] = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, future=True, connect_args=connect_args)


class Store:
    def __init__(self, url: str = "sqlite:///./rag_eval.db") -> None:
        self.url = url
        self.engine = make_engine(url)
        Base.metadata.create_all(self.engine)
        self._session_factory = sessionmaker(self.engine, expire_on_commit=False, future=True)

    def session(self) -> Session:
        return self._session_factory()

    def create_dataset(
        self,
        rows: list[EvalRow],
        *,
        name: str,
        filename: str | None = None,
    ) -> Dataset:
        with self.session() as session:
            dataset = Dataset(
                id=_new_id(),
                name=name,
                filename=filename,
                row_count=len(rows),
            )
            session.add(dataset)
            for index, row in enumerate(rows):
                session.add(
                    DatasetRow(
                        id=_new_id(),
                        dataset_id=dataset.id,
                        row_index=index,
                        question=row.question,
                        ground_truth=row.ground_truth,
                        answer=row.answer,
                        retrieved_contexts=row.retrieved_contexts,
                    )
                )
            session.commit()
            session.refresh(dataset)
            return dataset

    def get_dataset(self, dataset_id: str) -> Dataset | None:
        with self.session() as session:
            return session.get(Dataset, dataset_id)

    def list_datasets(self) -> list[Dataset]:
        with self.session() as session:
            return list(session.scalars(select(Dataset).order_by(Dataset.created_at.desc())))

    def get_dataset_rows(self, dataset_id: str) -> list[EvalRow]:
        with self.session() as session:
            records = list(
                session.scalars(
                    select(DatasetRow)
                    .where(DatasetRow.dataset_id == dataset_id)
                    .order_by(DatasetRow.row_index)
                )
            )
            return [
                EvalRow(
                    question=record.question,
                    answer=record.answer,
                    retrieved_contexts=list(record.retrieved_contexts or []),
                    ground_truth=record.ground_truth,
                )
                for record in records
            ]

    def create_run(
        self,
        *,
        dataset_id: str,
        adapter_type: str,
        adapter_config: dict[str, Any] | None = None,
        evaluator: str,
        label: str | None = None,
        git_sha: str | None = None,
        status: str = "queued",
    ) -> Run:
        with self.session() as session:
            run = Run(
                id=_new_id(),
                dataset_id=dataset_id,
                adapter_type=adapter_type,
                adapter_config=adapter_config or {},
                evaluator=evaluator,
                label=label,
                git_sha=git_sha,
                status=status,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            return run

    def get_run(self, run_id: str) -> Run | None:
        with self.session() as session:
            stmt = select(Run).options(selectinload(Run.scores)).where(Run.id == run_id)
            return session.scalars(stmt).first()

    def list_runs(self, dataset_id: str | None = None) -> list[Run]:
        with self.session() as session:
            stmt = select(Run).order_by(Run.created_at.desc())
            if dataset_id:
                stmt = stmt.where(Run.dataset_id == dataset_id)
            return list(session.scalars(stmt))

    def update_run(self, run_id: str, **fields: Any) -> Run | None:
        with self.session() as session:
            run = session.get(Run, run_id)
            if run is None:
                return None
            for key, value in fields.items():
                setattr(run, key, value)
            session.commit()
            session.refresh(run)
            return run

    def complete_run(self, run_id: str, summary: MetricSummary) -> Run:
        with self.session() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise KeyError(run_id)
            run.status = "completed"
            run.means = summary.means
            run.error_count = summary.error_count
            run.completed_at = _utcnow()
            run.error_message = None
            for index, row in enumerate(summary.rows):
                session.add(
                    RunScore(
                        id=_new_id(),
                        run_id=run.id,
                        row_index=index,
                        question=row.question,
                        answer=row.answer,
                        retrieved_contexts=row.retrieved_contexts,
                        ground_truth=row.ground_truth,
                        metrics=row.metrics,
                        error=row.error,
                    )
                )
            session.commit()
            session.refresh(run)
            return run

    def fail_run(self, run_id: str, message: str) -> Run:
        with self.session() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise KeyError(run_id)
            run.status = "failed"
            run.error_message = message
            run.completed_at = _utcnow()
            session.commit()
            session.refresh(run)
            return run

    def set_baseline(self, run_id: str) -> Run:
        with self.session() as session:
            run = session.get(Run, run_id)
            if run is None:
                raise KeyError(run_id)
            others = session.scalars(
                select(Run).where(Run.dataset_id == run.dataset_id, Run.is_baseline.is_(True))
            )
            for other in others:
                other.is_baseline = False
            run.is_baseline = True
            session.commit()
            session.refresh(run)
            return run

    def get_run_scores(self, run_id: str) -> list[RowScore]:
        with self.session() as session:
            records = list(
                session.scalars(
                    select(RunScore).where(RunScore.run_id == run_id).order_by(RunScore.row_index)
                )
            )
            return [
                RowScore(
                    question=record.question,
                    answer=record.answer,
                    retrieved_contexts=list(record.retrieved_contexts or []),
                    ground_truth=record.ground_truth,
                    metrics=dict(record.metrics or {}),
                    error=record.error,
                )
                for record in records
            ]

    def snapshot(self, run_id: str) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return {
            "run_id": run.id,
            "dataset_id": run.dataset_id,
            "evaluator": run.evaluator,
            "adapter_type": run.adapter_type,
            "label": run.label,
            "git_sha": run.git_sha,
            "status": run.status,
            "means": run.means or {},
            "error_count": run.error_count,
            "is_baseline": run.is_baseline,
        }
