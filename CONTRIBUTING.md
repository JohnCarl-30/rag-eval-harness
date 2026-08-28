# Contributing to rag-eval-harness

This is an evaluation orchestrator, not a RAG framework. Please keep PRs inside that boundary.

## Setup

Python 3.11+ and [uv](https://docs.astral.sh/uv/). Node 20+ for the UI.

```bash
uv sync
uv run pytest
uv run ruff check src tests
cd web && npm install && npm run build
```

## Layout

- `src/rag_eval_harness`: library, CLI, FastAPI
- `web/`: Vite + React
- `examples/dummy-rag`: canned HTTP SUT + 16-row fixture
- `tests/`: pytest (no network; RAGAS mocked; stub evaluator)

## PR checklist

- Tests for store / adapters / evaluators / regression / CLI when you touch them
- Stub evaluator remains the default CI path
- Do not add Redis, ingestion, or a vector store

## License

MIT. By contributing you agree your work is licensed under the MIT License.
