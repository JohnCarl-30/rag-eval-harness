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

From another repo, after this project is tagged. `stub` is smoke. Use `lexical` when the gate should mean overlap, not hashes.

```yaml
- uses: JohnCarl-30/rag-eval-harness@v0.1.0
  with:
    traces: tests/golden/traces.jsonl
    evaluator: lexical
    baseline: tests/golden/baseline.json
    output: rag-eval-results.json
```

Inputs:

| Input | Default | Notes |
| --- | --- | --- |
| `traces` | | Precomputed traces file |
| `dataset` | | Golden questions; use with `sut-url` |
| `sut-url` | | HTTP adapter |
| `evaluator` | `stub` | `stub`, `lexical`, or `ragas` |
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
rag-eval eval traces.jsonl --evaluator lexical -o tests/golden/baseline.json
```

## This repository's CI

On push and pull request:

1. `ruff check` and `pytest` (stub evaluator; RAGAS mocked)
2. `npm run build` in `web/`
3. `docker compose` smoke: API health, dummy-rag, stub eval via HTTP

RAGAS live scoring is not required to merge.

Relaydesk (the support widget) runs its own gate: `eval/golden.csv` against `POST /api/eval`, then `rag-eval regress` vs `eval/baseline.json`. See [nimbus-case-study.md](nimbus-case-study.md) (weaker `k`) and [nimbus-chunking.md](nimbus-chunking.md) (paragraph index). Both fail the same 0.05 recall gate. Production stayed on title-boosted top-3 articles. Why the job uses lexical, not RAGAS: [nimbus-cost.md](nimbus-cost.md). When overlap and a judge fight: [nimbus-judge.md](nimbus-judge.md).

## PyPI (optional)

`pip install rag-eval-harness` stays a git URL until trusted publishing is on.

1. Create a PyPI account and an empty project named `rag-eval-harness` (or let the first trusted upload create it).
2. PyPI → Publishing → GitHub → repository `JohnCarl-30/rag-eval-harness`, workflow `release.yml`, environment `pypi`.
3. In this GitHub repo: Settings → Environments → `pypi` (matches [`.github/workflows/release.yml`](../.github/workflows/release.yml)).
4. Re-run the `v0.1.0` release workflow, or tag `v0.1.1`.
