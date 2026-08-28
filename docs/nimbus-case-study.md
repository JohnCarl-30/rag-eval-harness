# Nimbus case study

The support widget in **Relaydesk** (`~/Documents/relaydesk`) is the system under test. This repo only scores it.

**Question:** if we weaken retrieval (top-1, no title boost), does help-center quality drop enough that CI should fail?

**Answer:** yes. Mean **context recall** fell from **0.880 to 0.740** (Δ **-0.140**). `rag-eval regress --threshold 0.05` exits **1**.

## Setup

- Golden set: 40 questions against the seeded Nimbus help center ([`golden.csv`](../examples/nimbus/golden.csv) as of 2026-08-27). 36 are in-corpus; 4 are out of scope. The live CSV is now 50 rows. See [reasons.md](../examples/nimbus/reasons.md). The snapshots below are the original 40.
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

What we did next on the product: title-boosted top-3 stays in production. Relaydesk CI calls this harness against `/api/eval` and fails the PR if recall drops more than 0.05 vs the committed baseline.

## Record / post

```bash
./scripts/demo.sh
```

That command is the 90-second clip: means print, `context_recall FAIL`, exit 1.

Copy for LinkedIn (edit the first line if you want):

> I gated a support bot on retrieval quality, not vibes.
> 40 Nimbus help-center questions. Weakening the retriever (top-1, no title boost) cut mean context recall 0.88 → 0.74. CI failed at a 0.05 threshold.
> Harness: https://github.com/JohnCarl-30/rag-eval-harness
> Case study: https://github.com/JohnCarl-30/rag-eval-harness/blob/main/docs/nimbus-case-study.md
> Resume: Shipped a RAG eval harness and gated a support bot: a weaker retriever cut mean context recall 0.88 → 0.74 and failed CI at a 0.05 threshold (40-row golden set).

The second incident is the index, not k. [Chunking case study](nimbus-chunking.md).
