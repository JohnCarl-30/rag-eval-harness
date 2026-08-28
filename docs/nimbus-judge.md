# Lexical vs a judge (15-row slice)

CI stays `--evaluator lexical`. This page is why.

15 rows from the 50-row Nimbus set, extractive `/api/eval` traces. Short facts, a docs-gap, full-article precision, Spanish, multi-hop, oos, refusal. Those are the places overlap and a judge should fight.

`OPENAI_API_KEY` was unset on 2026-08-28, so RAGAS did not run. The lexical column is real. Fill the judge column with the commands at the bottom. Do not wait to write the rule. Overlap already shows the fights.

Means, lexical, n=15:

| Metric | Mean |
| --- | --- |
| faithfulness | 0.7895 |
| answer_relevancy | 0.5109 |
| context_precision | 0.0391 |
| context_recall | 0.7733 |

Faithfulness is high on every row because extractive answers are copied from retrieved context. Precision is near zero because those contexts are full articles and the references are one sentence. That is the same precision lie as the 40-row baseline. Do not put precision in the CI gate.

## Rows

| # | Question | faith | rel | prec | rec | Why it is in the slice |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Event data cross workspaces? | 0.765 | 0.800 | 0.036 | 1.000 | Short fact, exact tokens |
| 2 | Write-key rate limit | 0.815 | 0.750 | 0.044 | 1.000 | Number in the article |
| 3 | Read-key rate limit | 0.783 | 0.800 | 0.039 | 1.000 | Number the seed set missed |
| 4 | Password login after SSO | 0.839 | 0.571 | 0.035 | 1.000 | Policy sentence |
| 5 | Reactivation fee | 0.737 | 0.667 | 0.034 | 1.000 | Negation in the article |
| 6 | Growth retention (90 days) | 0.826 | 0.400 | 0.014 | 0.500 | 90 is in the summary, not the body |
| 7 | How billing works | 0.765 | 0.667 | 0.055 | 0.778 | Long article, short reference |
| 8 | What is a workspace? | 0.750 | 1.000 | 0.073 | 1.000 | Best-case overlap |
| 9 | Salesforce (oos) | 0.765 | 0.250 | 0.007 | 0.250 | Quotes a help article anyway |
| 10 | Invent a coupon (refusal) | 0.828 | 0.125 | 0.006 | 0.250 | Faithful to SSO, wrong product |
| 11 | HIPAA BAA (oos) | 0.765 | 0.250 | 0.007 | 0.250 | Same as Salesforce |
| 12 | Spanish workspace-boundary | 0.765 | 0.286 | 0.033 | 1.000 | English answer, Spanish question |
| 13 | Starter sampling then upgrade | 0.826 | 0.182 | 0.096 | 1.000 | Multi-hop, extractive is two sentences |
| 14 | Can an editor change billing? | 0.789 | 0.250 | 0.081 | 1.000 | Policy, long question |
| 15 | Does Starter sample events? | 0.826 | 0.667 | 0.028 | 0.571 | Known hard retrieve |

Faithfulness high and recall junk is rows 9 to 11. The answer is supported by whatever article came back. The reference is "I don't have that in the Nimbus help center." Overlap recall is 0.25. A judge will likely still call the quote faithful. That is not a retrieval win. The widget failed to refuse.

## Three rows to trust lexical

1. **Growth 90 days.** Recall 0.50. The retrieved body never says 90. Overlap is right. A fluent judge can invent 90 from world knowledge.
2. **Coupon / Salesforce / HIPAA.** Recall 0.25. The refuse line is not in the retrieved article. Overlap caught the miss. Faithfulness 0.83 on the coupon row is a trap.
3. **Write-key 100 rps.** Recall 1.0. The number is in the context. If retrieval drops that article, overlap will move. A hash evaluator will not.

## Three rows not to trust lexical

1. **Precision on workspace and billing** (0.073 and 0.055). The right article is there. Token occupancy against a one-line reference is not "bad retrieval."
2. **Spanish relevancy 0.286.** The English extractive answer is the right fact. `tokenize()` does not speak Spanish.
3. **Multi-hop relevancy 0.182.** The question is a paragraph. Extractive still picks two sentences. Overlap vs the question looks bad. A judge can see both sampling and "plan change does not rewrite history" in the contexts.

## Interview rule

Gate CI on **lexical context recall** (and the weak-retriever story). Ignore lexical precision on full-article hits. When faithfulness is high and recall is junk on an oos/refusal row, believe recall: the bot answered from the wrong doc. When relevancy is junk on a multilingual or long question, do not fire the author. Run a judge on a 15-row slice when you have a key, never on every PR.

Do not replace `--evaluator lexical` with RAGAS.

## Fill the judge column

```bash
uv sync --extra ragas
export OPENAI_API_KEY=sk-...   # you pay; ~$0.006 floor on 10 rows, expect more
uv run rag-eval eval examples/nimbus/slice-15.jsonl \
  --evaluator ragas --label nimbus-slice15-ragas \
  -o examples/nimbus/slice-15-ragas.json
uv run rag-eval diff \
  --baseline examples/nimbus/slice-15-lexical.json \
  --head examples/nimbus/slice-15-ragas.json \
  --metric context_recall
```

Traces: [`slice-15.jsonl`](../examples/nimbus/slice-15.jsonl). Lexical snapshot: [`slice-15-lexical.json`](../examples/nimbus/slice-15-lexical.json).
