# Metrics and evaluators

## Metrics

Always computed:

- **faithfulness** — is the answer supported by retrieved context?
- **answer_relevancy** — does the answer address the question?

When any row has `ground_truth` / `reference`:

- **context_precision**
- **context_recall**

Rows without ground truth omit the context metrics. Means are the average over successful rows only. If every row errors, required means are `0.0`.

## Stub evaluator

Default. No judge key. Hashes `question` / `answer` / contexts / ground truth into stable scores in `[0.5, 1.0]`. Use it for demos, UI wiring, and CI that should not call a model.

```bash
rag-eval eval traces.jsonl --evaluator stub
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

Means only. Per-row diffs belong in the UI.

```bash
rag-eval baseline <run-id>
rag-eval regress --baseline <run-id-or.json> --head <run-id-or.json> --threshold 0.05
```

Exit `1` if any baseline mean minus head mean is **greater than** `--threshold`. A missing head metric is treated as `0.0`.
