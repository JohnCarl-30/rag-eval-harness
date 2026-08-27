# rag-eval-harness

RAGAS with a memory and a diff view.

Upload a golden RAG dataset, run a pipeline (precomputed traces or HTTP), score with **RAGAS** or a keyless **stub** evaluator, persist runs, and fail CI when mean metrics drop versus a tagged baseline.

This is not a RAG framework. There is no ingestion or retrieval stack. Evaluation orchestration is the product.

## 10-minute path

Requires Python 3.11+ ([uv](https://docs.astral.sh/uv/) recommended) and, for the UI, Node 20+.

```bash
git clone https://github.com/JohnCarl-30/rag-eval-harness.git && cd rag-eval-harness
uv sync
```

Score the bundled traces (no API key, no network):

```bash
uv run rag-eval eval examples/dummy-rag/traces.jsonl --evaluator stub -o /tmp/rag-eval-head.json
```

You should see a run id and means for faithfulness, answer relevancy, context precision, and context recall.

Optional — call a live HTTP SUT (the canned FAQ server):

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
pip install git+https://github.com/JohnCarl-30/rag-eval-harness.git
pip install 'rag-eval-harness[ragas]'   # after a PyPI release, or: pip install '.[ragas]' from a clone
```

```bash
rag-eval eval traces.jsonl --evaluator stub
rag-eval eval golden.csv --sut-url https://your-rag.example/query --sut-token "$TOKEN"
rag-eval baseline <run-id>
rag-eval regress --baseline <run-id-or.json> --head <run-id-or.json> --threshold 0.05
rag-eval serve
```

`regress` exits **1** if any mean drops by more than `--threshold` (default `0.05`).

## Contracts

| Piece | Behavior |
| --- | --- |
| Columns | `question` required. Optional `ground_truth`. Traces also need `answer` and `retrieved_contexts` (JSON list or `\|` / newline delimited). Aliases: `user_input`, `reference`, `response`, `contexts`. |
| HTTP SUT | `POST {"question"}` → `{"answer","retrieved_contexts"}`. Optional bearer. Per-row timeout; a failed row is an error, the run continues. |
| Metrics | Always faithfulness + answer relevancy. Context precision + context recall when `ground_truth` is present. |
| Evaluators | `stub` (stable hashes, CI smoke), `lexical` (token overlap vs context — use this for real gates), `ragas` (`OPENAI_API_KEY`, optional `OPENAI_BASE_URL`). |
| Store | SQLite default (`DATABASE_URL`). Postgres via `postgresql+psycopg://…`. |
| Jobs | In-process. **100-row cap.** No Redis. |
| Auth | Open on loopback. `RAG_EVAL_API_KEY` required when binding a non-loopback address. |
| Regression | Tag a run as baseline. Gate on **mean** delta. Per-row diffs are UI-only. |

Docs: [adapters](docs/adapters.md) · [metrics](docs/metrics.md) · [CI](docs/ci.md) · [storage](docs/storage.md) · [Nimbus case study](docs/nimbus-case-study.md)

## GitHub Action

After this repo is on GitHub:

```yaml
- uses: JohnCarl-30/rag-eval-harness@v0.1.0
  with:
    traces: tests/golden/traces.jsonl
    evaluator: stub
    baseline: tests/golden/baseline.json
    threshold: "0.05"
```

See [docs/ci.md](docs/ci.md).

## Development

```bash
uv sync
uv run pytest
uv run ruff check src tests
cd web && npm install && npm run build
docker compose up --build   # then ./scripts/smoke.sh
```

## License

MIT. See [CHANGELOG](CHANGELOG.md) and [CONTRIBUTING](CONTRIBUTING.md).
