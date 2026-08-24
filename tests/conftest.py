from __future__ import annotations

from pathlib import Path

import pytest

from rag_eval_harness.store.repo import Store

FIXTURES = Path(__file__).resolve().parents[1] / "examples" / "dummy-rag"


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store(f"sqlite:///{tmp_path / 'test.db'}")


@pytest.fixture
def golden_csv() -> Path:
    return FIXTURES / "golden.csv"


@pytest.fixture
def traces_jsonl() -> Path:
    return FIXTURES / "traces.jsonl"
