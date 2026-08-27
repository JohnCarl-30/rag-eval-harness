# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-08-27

### Added

- Python package `rag-eval-harness` with CLI `rag-eval` (eval, baseline, regress, serve, runs)
- Trace and HTTP adapters, stub evaluator, lexical overlap evaluator, RAGAS collections wrapper (`[ragas]` extra)
- SQLite/Postgres SQLAlchemy store, 100-row cap, mean-delta regression gate
- FastAPI + React UI for datasets, runs, and diffs
- Loopback-open / non-loopback API-key auth
- Dummy FAQ RAG example and 15-row golden set
- Nimbus 40-row golden set, lexical case study, and committed baseline/weak snapshots
- Consumer GitHub Action, project CI, Compose smoke path
- PyPI trusted publisher + GHCR image on `v*` tags
