# Nimbus case study

The support widget in **Relaydesk** (`~/Documents/relaydesk`) is the system under test. This repo only scores it.

**Question:** if we weaken retrieval (top-1, no title boost), does help-center quality drop enough that CI should fail?

**Answer:** yes. Mean **context recall** fell from **0.880 to 0.740** (Δ **-0.140**). `rag-eval regress --threshold 0.05` exits **1**.

## Setup

- Golden set: 40 questions against the seeded Nimbus help center ([`golden.csv`](../examples/nimbus/golden.csv)). 36 are in-corpus; 4 are out of scope.
- SUT: `POST /api/eval` with `{"question"}` → `{"answer","retrieved_contexts"}`. Extractive answers, no judge LLM.
- Scorer: `--evaluator lexical` (token overlap). Stub hashes are for keyless UI/CI smoke, not this report.
- Baseline retriever: top-3, title weight 4.
- Weak retriever: top-1, title weight 0 (`?variant=weak`).

## Numbers (2026-08-27)

| Metric | Baseline | Weak retriever | Delta | Gate (0.05) |
| --- | --- | --- | --- | --- |
| context_recall | 0.8799 | 0.7399 | -0.140 | FAIL |
| faithfulness | 0.7772 | 0.7542 | -0.023 | ok |
| answer_relevancy | 0.6381 | 0.5985 | -0.040 | ok |
| context_precision | 0.0634 | 0.1227 | +0.059 | ok |

Context precision is low on both sides because retrieved chunks are full articles and the reference answers are short. The gate that matters here is **recall**: the weak retriever drops the article the reference needs.

Snapshots: [`baseline.json`](../examples/nimbus/baseline.json), [`weak.json`](../examples/nimbus/weak.json).

## Reproduce

```bash
# terminal 1
cd ~/Documents/relaydesk && npm run dev

# terminal 2
cd ~/Documents/agentic-system
uv run rag-eval eval examples/nimbus/golden.csv \
  --sut-url http://127.0.0.1:3000/api/eval \
  --evaluator lexical --label nimbus-baseline -o /tmp/nimbus-baseline.json
uv run rag-eval eval examples/nimbus/golden.csv \
  --sut-url 'http://127.0.0.1:3000/api/eval?variant=weak' \
  --evaluator lexical --label nimbus-weak -o /tmp/nimbus-weak.json
uv run rag-eval regress \
  --baseline /tmp/nimbus-baseline.json \
  --head /tmp/nimbus-weak.json \
  --threshold 0.05
# expected: exit 1, context_recall FAIL
```

What we would do next on the product: keep title-boosted top-3 in production; add a CI job on Relaydesk that calls this harness against `/api/eval` and fails the PR if recall drops more than 0.05 vs the committed baseline.
