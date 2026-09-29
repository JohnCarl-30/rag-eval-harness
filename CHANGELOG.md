# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-09-29

### Added

- `rag-eval investigate` and the `agent` extra. After the `regress` gate fails, a LangGraph graph triages failing means by stage, runs one Pydantic AI diagnoser per stage in parallel, and summarizes. Exit codes match `regress`. See [docs/agent.md](docs/agent.md).
- `investigate --mode supervisor`: one Pydantic AI agent with read-only tools (`failing_metrics`, `worst_rows`, `row_detail`) that delegates to the diagnoser via `diagnose_stage`. One budget covers the supervisor and its delegates.
- `investigate --trace` writes each agent run's messages, tool calls, tokens, and time as JSON. `--otel` sends spans via Logfire or OTLP (`trace` extra).

### Fixed

- The HTTP adapter treats a blank `answer` as a row error.
- HTTP adapter row errors no longer include the SUT URL. API responses redact tokens and strip userinfo, query, and fragment from adapter URLs.

## [0.1.1] - 2026-09-26 (never tagged; shipped in 0.2.0)

Upgrade from 0.1.0: it serves any file on disk to unauthenticated requests when `web/dist` is present (the Docker image), and allows every origin via CORS.

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

- Security: the SPA fallback route served any file on disk via an encoded `../` path (for example `/..%2f..%2fproc/self/environ`), without an API key. It now only serves files inside `web/dist`.
- Security: CORS allowed every origin, so any website could read an open loopback API and create HTTP runs against arbitrary URLs. Cross-origin access is now off unless `RAG_EVAL_CORS_ORIGINS` is set.
- `regress` (and the API/UI diff) passed when head errored on most rows, because means skip errored rows. Head with more errored rows than baseline now fails the gate.
- `diff` and the UI Diff page paired rows by position, so a reordered or edited golden set compared unrelated questions. Rows now pair by question text; added or removed questions show with one side empty.
- `diff` printed per-row drops with a plus sign (`(+1.0000)` for 1.0 → 0.0). They now print as negative deltas, like the mean table.
- Uploading an empty non-CSV file returned a 500. It is now a 400 "File is empty."
- API/UI uploads named datasets `golden.csv` while the CLI named them `golden`. Both use the file stem.
- Only a completed run can be tagged as baseline (CLI exits 2, API returns 409).
- Every CLI `eval` created a new dataset, so baseline tags never grouped runs. Re-evaluating identical rows under the same name now reuses the dataset.
- Runs left `queued`/`running` by a stopped server stayed that way forever. `rag-eval serve` marks them failed on startup.
- Empty `DATABASE_URL` (GitHub Actions passes `""` when the input is unset) is treated as the default SQLite file. The consumer Action was failing `create_engine` on every CI run.
- README and SECURITY still talked as if the GitHub repository did not exist.
- Lexical faithfulness scored every correct refusal near zero, so a pipeline that learned to refuse out-of-scope questions failed the gate (Relaydesk: 0.7049 vs 0.7823). Rows marked `abstained` (alias `escalated`, from the HTTP response or a traces column) now skip faithfulness and answer relevancy; context metrics still apply. See [metrics](docs/metrics.md#abstained-rows).
- `v0.1.0` never reached PyPI: the trusted publisher was not registered, so the upload failed with `invalid-publisher`. `docs/ci.md` now spells out the pending-publisher step.

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
