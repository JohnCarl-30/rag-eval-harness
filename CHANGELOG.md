# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Nimbus chunking case study and committed `chunked.json` / `hybrid-chunked.json` snapshots. Precision rose, recall failed the 0.05 gate, production stayed on articles.
- Nimbus cost/p95 log. Extractive `/api/eval` is 0.12 ms/row and $0. Lexical stays the PR gate.
- Nimbus golden set grew to 50 rows with [reasons.md](examples/nimbus/reasons.md). Case-study snapshots stay on the original 40. `baseline-50.json` is the new lexical lock.
- Nimbus 15-row lexical vs judge slice ([docs/nimbus-judge.md](docs/nimbus-judge.md)). RAGAS not run; no API key. CI stays lexical.
- `rag-eval diff` prints mean deltas and the worst per-row metric drops. It does not fail CI; `regress` still owns the gate.
- `lexical` evaluator in the HTTP API and React UI. CLI already had it.
- Spanish FAQ row in the dummy-rag fixture.
- Clone path starts at `./scripts/demo.sh` so the first command is the Nimbus recall fail. CI runs that script so the red gate cannot rot.

### Fixed

- Empty `DATABASE_URL` (GitHub Actions passes `""` when the input is unset) is treated as the default SQLite file. The consumer Action was failing `create_engine` on every CI run.
- README and SECURITY still talked as if the GitHub repository did not exist.

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
