# rag-eval-harness

[![CI](https://github.com/JohnCarl-30/rag-eval-harness/actions/workflows/ci.yml/badge.svg)](https://github.com/JohnCarl-30/rag-eval-harness/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/rag-eval-harness)](https://pypi.org/project/rag-eval-harness/)
[![Python](https://img.shields.io/pypi/pyversions/rag-eval-harness)](https://pypi.org/project/rag-eval-harness/)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue)](LICENSE)

**Your RAG got worse. Your tests stayed green.**

A regression gate for RAG pipelines. Score a golden set, keep every run, and fail CI when retrieval or answers slip against a tagged baseline. RAGAS with a memory and a diff view.

```text
$ rag-eval regress --baseline examples/nimbus/baseline.json --head examples/nimbus/weak.json
threshold: 0.05
  answer_relevancy     baseline=0.6381  head=0.5985  delta=-0.0396  ok
  context_precision    baseline=0.0634  head=0.1227  delta=+0.0592  ok
  context_recall       baseline=0.8799  head=0.7399  delta=-0.1399  FAIL
  faithfulness         baseline=0.7772  head=0.7542  delta=-0.0230  ok
  errored rows         baseline=0  head=0  ok
Regression detected.                                          # exit 1
```

```bash
pip install rag-eval-harness
```

No API key needed: the `lexical` evaluator gates on token overlap, and `stub` runs keyless CI smoke. Add `[ragas]` for LLM-judge metrics or `[agent]` for `rag-eval investigate`, which explains why a gate failed.

**What this proved:** a weaker retriever on a 40-question Nimbus help-center set cut mean **context recall from 0.880 to 0.740**. `rag-eval regress --threshold 0.05` exited **1**. Full write-up: [Nimbus case study](docs/nimbus-case-study.md). 90-second recording: `./scripts/demo.sh`.

Chunking the same corpus doubled lexical precision and failed the recall gate. Production stayed on whole articles. [Chunking case study](docs/nimbus-chunking.md). `./scripts/demo-chunking.sh`.

This is not a RAG framework. There is no ingestion or retrieval stack. Evaluation orchestration is the product.

## 10-minute path

Requires Python 3.11+ ([uv](https://docs.astral.sh/uv/) recommended) and, for the UI, Node 20+.

```bash
git clone https://github.com/JohnCarl-30/rag-eval-harness.git && cd rag-eval-harness
uv sync
./scripts/demo.sh
```

You should see `context_recall` FAIL (0.880 → 0.740) and the script exit 0. That red `rag-eval regress` is the product. No API key. Then score dummy traces if you want a green run:

```bash
uv run rag-eval eval examples/dummy-rag/traces.jsonl --evaluator stub -o /tmp/rag-eval-head.json
```

Optional. Call a live HTTP SUT (the canned FAQ server):

```bash
python3 examples/dummy-rag/server.py --port 8080 &
uv run rag-eval eval examples/dummy-rag/golden.csv \
  --sut-url http://127.0.0.1:8080/query \
  --evaluator stub
```

UI (dev):

```bash
uv run rag-eval serve          # API on 127.0.0.1:8000, open on loopback (no API key)
cd web && npm install && npm run dev   # Vite on :5173, proxies /api
```

Open http://127.0.0.1:5173, upload `examples/dummy-rag/traces.jsonl` or `golden.csv`, create a run, tag a baseline, open Diff.

Docker:

```bash
cp .env.example .env          # set RAG_EVAL_API_KEY (required: the API binds 0.0.0.0)
docker compose up --build
# UI+API: http://127.0.0.1:8000   dummy RAG: http://127.0.0.1:8080/query
```

## Install

```bash
pip install rag-eval-harness            # core: stub + lexical evaluators, store, gate, UI API
pip install 'rag-eval-harness[ragas]'   # RAGAS judge metrics (OPENAI_API_KEY)
pip install 'rag-eval-harness[agent]'   # rag-eval investigate
```

```bash
rag-eval eval traces.jsonl --evaluator stub
rag-eval eval golden.csv --sut-url https://your-rag.example/query --sut-token "$TOKEN"
rag-eval baseline <run-id>
rag-eval regress --baseline <run-id-or.json> --head <run-id-or.json> --threshold 0.05
rag-eval diff --baseline <run-id-or.json> --head <run-id-or.json>
rag-eval investigate --baseline <run-id-or.json> --head <run-id-or.json>   # needs [agent]
rag-eval investigate ... --mode supervisor --trace trace.json
rag-eval serve
```

`regress` exits **1** if any mean drops by more than `--threshold` (default `0.05`), or if head has more errored rows than baseline (means skip errored rows, so a timing-out SUT would otherwise pass). `diff` prints the same means plus the worst per-row drops (rows paired by question) and always exits 0 on a successful compare.

`investigate` runs the `regress` gate, then a LangGraph fan-out of Pydantic AI agents explains a failure: one diagnosis per failing stage (retrieval, generation), then a summary. `--mode supervisor` swaps the fixed graph for one agent that picks its own tools. `--trace` writes every agent run as JSON; `--otel` sends spans via Logfire. Same exit codes as `regress`. Install with `pip install 'rag-eval-harness[agent]'`. See [docs/agent.md](docs/agent.md).

## Contracts

| Piece | Behavior |
| --- | --- |
| Columns | `question` required. Optional `ground_truth`. Traces also need `answer` and `retrieved_contexts` (JSON list or `\|` / newline delimited). Aliases: `user_input`, `reference`, `response`, `contexts`. |
| HTTP SUT | `POST {"question"}` → `{"answer","retrieved_contexts"}`. Optional bearer. Per-row timeout; a failed row is an error, the run continues. |
| Metrics | Always faithfulness + answer relevancy. Context precision + context recall when `ground_truth` is present. `lexical` and `ragas` add keyless `recall_at_k` and `mrr` from `reference_contexts` labels or ground truth ([details](docs/metrics.md#retrieval-metrics)). |
| Evaluators | `stub` (stable hashes, CI smoke), `lexical` (token overlap vs context, use this for real gates), `ragas` (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`). |
| Store | SQLite default (`DATABASE_URL`). Postgres via `postgresql+psycopg://…`. |
| Jobs | In-process. **100-row cap.** No Redis. |
| Auth | Open on loopback. `RAG_EVAL_API_KEY` required when binding a non-loopback address. No cross-origin access unless `RAG_EVAL_CORS_ORIGINS` lists origins (comma-separated). |
| Regression | Tag a run as baseline. Gate on **mean** delta and errored-row count. Per-row drops show in `diff` and the UI; they never fail the gate. |

## Why not DeepEval, promptfoo, or RAGAS?

Use them. This sits next to them.

| Tool | What it is | What this adds |
| --- | --- | --- |
| RAGAS | A metrics library: faithfulness, context recall, and more | Runs RAGAS as one evaluator, then stores the run, diffs it against a baseline, and gates CI on the delta |
| DeepEval | pytest-style assertions with per-case thresholds | A gate on **change** versus a tagged baseline, not on absolute scores you have to tune |
| promptfoo | Config-driven prompt and model comparison, red teaming | RAG-specific: retrieved contexts, ground truth, per-row retrieval drops |

Two things the others do not ship: a keyless `lexical` gate (no judge model to drift or cost money in CI), and `investigate`, which reads the rows that dropped and tells you whether retrieval or generation broke.

Docs: [adapters](docs/adapters.md) · [metrics](docs/metrics.md) · [CI](docs/ci.md) · [investigator](docs/agent.md) · [storage](docs/storage.md) · [Nimbus case study](docs/nimbus-case-study.md) · [Chunking case study](docs/nimbus-chunking.md) · [Cost and p95](docs/nimbus-cost.md) · [Lexical vs judge](docs/nimbus-judge.md)

## GitHub Action

`stub` is keyless CI smoke. Hashes look healthy on junk contexts. Use `lexical` for a real gate.

```yaml
- uses: JohnCarl-30/rag-eval-harness@v0.2.0
  with:
    traces: tests/golden/traces.jsonl
    evaluator: lexical
    baseline: tests/golden/baseline.json
    threshold: "0.05"
```

Public consumer: [Relaydesk](https://github.com/JohnCarl-30/relaydesk) fails PRs when Nimbus recall drops. See [docs/ci.md](docs/ci.md).

## Development

```bash
uv sync --extra agent   # without the extra, tests/test_agent.py is skipped
uv run pytest
uv run ruff check src tests
cd web && npm install && npm run build
docker compose up --build   # then ./scripts/smoke.sh
```

## License

MIT. See [CHANGELOG](CHANGELOG.md) and [CONTRIBUTING](CONTRIBUTING.md).
