from __future__ import annotations

import pytest

from rag_eval_harness.io import (
    LoadError,
    RowCapError,
    load_csv_text,
    load_jsonl_text,
    load_path,
    load_text,
)
from rag_eval_harness.types import ROW_CAP


def test_csv_aliases() -> None:
    text = (
        "user_input,reference,response,contexts\n"
        'What is PTO?,20 days,Staff get 20 PTO days,"handbook|policy"\n'
    )
    rows = load_csv_text(text)
    assert len(rows) == 1
    assert rows[0].question == "What is PTO?"
    assert rows[0].ground_truth == "20 days"
    assert rows[0].answer == "Staff get 20 PTO days"
    assert rows[0].retrieved_contexts == ["handbook", "policy"]


def test_jsonl_and_json_contexts() -> None:
    text = '{"question": "Q", "answer": "A", "retrieved_contexts": ["c1", "c2"]}\n'
    rows = load_jsonl_text(text)
    assert rows[0].retrieved_contexts == ["c1", "c2"]


def test_json_array() -> None:
    rows = load_text('[{"question": "Q1", "ground_truth": "G"}]', filename="data.json")
    assert rows[0].question == "Q1"
    assert rows[0].ground_truth == "G"


def test_skips_empty_questions() -> None:
    text = "question,answer\n,nope\nHello?,yes\n"
    rows = load_csv_text(text)
    assert len(rows) == 1
    assert rows[0].question == "Hello?"


def test_row_cap() -> None:
    lines = ["question"] + [f"q{i}" for i in range(ROW_CAP + 1)]
    with pytest.raises(RowCapError):
        load_csv_text("\n".join(lines))


def test_missing_question_column() -> None:
    with pytest.raises(LoadError):
        load_csv_text("foo,bar\n1,2\n")


def test_nimbus_golden_loads_under_cap() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    path = root / "examples" / "nimbus" / "golden.csv"
    rows = load_path(path)
    assert 50 <= len(rows) <= 100
    assert all(row.question for row in rows)
    assert sum(1 for row in rows if row.has_ground_truth()) == len(rows)
    reasons = (root / "examples" / "nimbus" / "reasons.md").read_text(encoding="utf-8")
    assert "multilingual" in reasons
    assert "docs-gap" in reasons


def test_nimbus_slice15_loads() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    rows = load_path(root / "examples" / "nimbus" / "slice-15.jsonl")
    assert len(rows) == 15
    assert all(row.question and row.answer and row.retrieved_contexts for row in rows)
    assert sum(1 for row in rows if row.has_ground_truth()) == 15
