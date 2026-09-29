# Metrics and evaluators

## Metrics

Always computed:

- faithfulness: is the answer supported by retrieved context?
- answer_relevancy: does the answer address the question?

When any row has `ground_truth` / `reference`:

- **context_precision**
- **context_recall**

With `lexical` or `ragas`, when a row has `reference_contexts` labels or ground truth:

- **recall_at_k**
- **mrr**

See [Retrieval metrics](#retrieval-metrics). Rows without ground truth omit the context metrics. Means are the average over successful rows only. If every row errors, required means are `0.0`.

### Abstained rows

A row marked `abstained` (alias `escalated`) omits faithfulness and answer relevancy; context metrics still apply. A refusal like "I don't have that in the help center" shares no words with the retrieved articles, so lexical faithfulness scored every correct refusal near zero, and a pipeline that learned to refuse out-of-scope questions failed the gate. Quoting the wrong article instead scored high ([nimbus-judge.md](nimbus-judge.md)). Measure whether it should have refused with a separate escalation check, not with faithfulness.

### Retrieval metrics

Classic search metrics over the passages the pipeline returned, with `k` = however many it returned. No judge, no key, same result every run.

- **recall_at_k**: share of the relevant passages that were retrieved.
- **mrr**: 1 / rank of the first relevant passage. `1.0` means it came back first; `0.0` means it never came back.

Which passages count as relevant:

1. **Labels.** Add a `reference_contexts` column (alias `relevant_contexts`; a JSON list or `|`-delimited). A retrieved passage matches a label when it contains the label text, ignoring case and whitespace. Use an article title, a doc ID, or a sentence that only that passage has. Recall is labels found / labels.
2. **Ground truth, when a row has no labels.** A passage counts when it holds at least half of the ground-truth tokens. Each row then has one implied relevant passage, so recall is `1.0` or `0.0`. This is a proxy: small chunks can each hold less than half the answer and read as misses, so label `reference_contexts` before trusting it on a chunked corpus.

On the 40-row Nimbus snapshots, ground-truth mode, lexical evaluator:

| Run | context_recall | recall_at_k | mrr |
| --- | --- | --- | --- |
| baseline | 0.880 | 0.900 | 0.817 |
| weak retriever | 0.740 | 0.700 | 0.700 |
| chunked | 0.782 | 0.700 | 0.617 |

The weak retriever loses the right article on one question in five. Chunking returns it lower in the list.

RAGAS adds these alongside its judge metrics, but only on rows the judge scored: a judge failure stays a row error.

## Stub evaluator

Default. No judge key. Hashes `question` / `answer` / contexts / ground truth into stable scores in `[0.5, 1.0]`. Use it for demos, UI wiring, and CI that should not call a model.

```bash
rag-eval eval traces.jsonl --evaluator stub
```

## Lexical evaluator

Token overlap. No judge key. Faithfulness is answer tokens found in retrieved context; context recall is ground-truth tokens found in context. Use this when you need a gate that actually moves when retrieval gets worse (see [Nimbus case study](nimbus-case-study.md) and [chunking](nimbus-chunking.md)).

On the 40-row Nimbus snapshot, lexical scoring is **1.6 ms** total. Stub is faster and reports a fake-healthy precision. RAGAS needs a key. Keep lexical as the PR evaluator. Numbers: [nimbus-cost.md](nimbus-cost.md). When overlap and a judge fight: [nimbus-judge.md](nimbus-judge.md).

```bash
rag-eval eval golden.csv --sut-url http://127.0.0.1:3000/api/eval --evaluator lexical
```

## RAGAS evaluator

Wraps the collections-style metrics API (`ragas.metrics.collections`), not the deprecated `evaluate()` helper.

```bash
pip install 'rag-eval-harness[ragas]'
export OPENAI_API_KEY=sk-...
# optional OpenAI-compatible proxy
export OPENAI_BASE_URL=https://api.openai.com/v1
export OPENAI_MODEL=gpt-4o-mini
export OPENAI_EMBEDDING_MODEL=text-embedding-3-small
rag-eval eval traces.jsonl --evaluator ragas
```

A live-judge test is skipped unless `OPENAI_API_KEY` is set. Unit tests inject fake metrics and never touch the network.

## Regression gate

Means only. Per-row diffs are in the UI and `rag-eval diff`. `regress` is the CI gate.

```bash
rag-eval baseline <run-id>
rag-eval regress --baseline <run-id-or.json> --head <run-id-or.json> --threshold 0.05
rag-eval diff --baseline <run-id-or.json> --head <run-id-or.json> --metric context_recall
```

Exit `1` if any baseline mean minus head mean is **greater than** `--threshold`. A missing head metric is treated as `0.0`.
