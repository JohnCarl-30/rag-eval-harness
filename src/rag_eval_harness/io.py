from __future__ import annotations

import csv
import io
import json
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from rag_eval_harness.types import COLUMN_ALIASES, ROW_CAP, EvalRow


class RowCapError(ValueError):
    pass


class LoadError(ValueError):
    pass


def _pick(record: Mapping[str, Any], logical: str) -> Any:
    for alias in COLUMN_ALIASES[logical]:
        if alias in record and record[alias] not in (None, ""):
            return record[alias]
        lower = {str(k).lower(): v for k, v in record.items()}
        if alias in lower and lower[alias] not in (None, ""):
            return lower[alias]
    return None


def parse_contexts(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return []
        if text.startswith("["):
            try:
                loaded = json.loads(text)
            except json.JSONDecodeError:
                loaded = None
            if isinstance(loaded, list):
                return [str(item).strip() for item in loaded if str(item).strip()]
        if "\n" in text:
            return [part.strip() for part in text.split("\n") if part.strip()]
        if "|" in text:
            return [part.strip() for part in text.split("|") if part.strip()]
        return [text]
    return [str(value)]


def record_to_row(record: Mapping[str, Any]) -> EvalRow | None:
    question = _pick(record, "question")
    if question is None or not str(question).strip():
        return None
    ground_truth = _pick(record, "ground_truth")
    answer = _pick(record, "answer")
    return EvalRow(
        question=str(question).strip(),
        answer=None if answer is None else str(answer),
        retrieved_contexts=parse_contexts(_pick(record, "retrieved_contexts")),
        ground_truth=None if ground_truth is None else str(ground_truth),
    )


def rows_from_records(records: Iterable[Mapping[str, Any]]) -> list[EvalRow]:
    rows: list[EvalRow] = []
    for record in records:
        row = record_to_row(record)
        if row is not None:
            rows.append(row)
    if not rows:
        raise LoadError("No rows with a question column were found.")
    if len(rows) > ROW_CAP:
        raise RowCapError(f"Row cap is {ROW_CAP}; got {len(rows)} rows.")
    return rows


def load_jsonl_text(text: str) -> list[EvalRow]:
    records: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            payload = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise LoadError(f"Invalid JSONL on line {line_no}: {exc}") from exc
        if not isinstance(payload, dict):
            raise LoadError(f"JSONL line {line_no} must be an object.")
        records.append(payload)
    return rows_from_records(records)


def load_json_text(text: str) -> list[EvalRow]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise LoadError(f"Invalid JSON: {exc}") from exc
    if isinstance(payload, dict) and "rows" in payload:
        payload = payload["rows"]
    if not isinstance(payload, list):
        raise LoadError("JSON input must be a list of objects or {\"rows\": [...]}.")
    records: list[dict[str, Any]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise LoadError("Each JSON row must be an object.")
        records.append(item)
    return rows_from_records(records)


def load_csv_text(text: str) -> list[EvalRow]:
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise LoadError("CSV is missing a header row.")
    records = [{k: v for k, v in row.items() if k is not None} for row in reader]
    return rows_from_records(records)


def load_text(text: str, *, filename: str = "upload.csv") -> list[EvalRow]:
    name = filename.lower()
    stripped = text.lstrip("\ufeff")
    if name.endswith(".jsonl") or name.endswith(".ndjson"):
        return load_jsonl_text(stripped)
    if name.endswith(".json"):
        return load_json_text(stripped)
    if stripped.lstrip().startswith("{") or stripped.lstrip().startswith("["):
        try:
            return load_json_text(stripped)
        except LoadError:
            return load_jsonl_text(stripped)
    if name.endswith(".csv") or "," in stripped.splitlines()[0]:
        return load_csv_text(stripped)
    return load_jsonl_text(stripped)


def load_path(path: str | Path) -> list[EvalRow]:
    file_path = Path(path)
    if not file_path.is_file():
        raise LoadError(f"File not found: {file_path}")
    return load_text(file_path.read_text(encoding="utf-8"), filename=file_path.name)
