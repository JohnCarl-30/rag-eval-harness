from __future__ import annotations

from rag_eval_harness.config import SQLITE_DEFAULT, Settings, clear_settings_cache


def test_blank_database_url_falls_back_to_sqlite(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "")
    clear_settings_cache()
    assert Settings().database_url == SQLITE_DEFAULT
