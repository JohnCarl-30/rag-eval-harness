# CI

## Official GitHub Action

From a checkout of this repository:

```yaml
- uses: ./
  with:
    traces: examples/dummy-rag/traces.jsonl
    evaluator: stub
    baseline: path/to/baseline.json
    threshold: "0.05"
    package: .
```

From another repo, after this project is tagged:

```yaml
- uses: JohnCarl-30/rag-eval-harness@v0.1.0
  with:
    traces: tests/golden/traces.jsonl
    evaluator: stub
    baseline: tests/golden/baseline.json
    output: rag-eval-results.json
```

Inputs:

| Input | Default | Notes |
| --- | --- | --- |
| `traces` | | Precomputed traces file |
| `dataset` | | Golden questions; use with `sut-url` |
| `sut-url` | | HTTP adapter |
| `evaluator` | `stub` | `stub` or `ragas` |
| `baseline` | | Run id or JSON snapshot with `means` |
| `threshold` | `0.05` | Mean drop that fails the job |
| `output` | `rag-eval-results.json` | Written for artifacts / next baseline |
| `package` | `rag-eval-harness` | Use `.` when testing this repo |
| `extra` | | e.g. `[ragas]` |
| `openai-api-key` | | Passed through for the ragas evaluator |
| `python-version` | `3.12` | |

The action runs `rag-eval eval` then, if `baseline` is set, `rag-eval regress` (exit 1 on drop).

Commit a snapshot from a known-good run as `baseline.json`:

```bash
rag-eval eval traces.jsonl --evaluator stub -o tests/golden/baseline.json
```

## This repository's CI

On push and pull request:

1. `ruff check` and `pytest` (stub evaluator; RAGAS mocked)
2. `npm run build` in `web/`
3. `docker compose` smoke: API health, dummy-rag, stub eval via HTTP

RAGAS live scoring is not required to merge.
