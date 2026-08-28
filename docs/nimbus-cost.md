# Nimbus cost and p95

Lexical stays the PR gate. gpt-4o-mini on this 40-row set is about **$0.007** for generate+rewrite and about **$0.02** as a RAGAS token floor. Money is not the constraint. Wall clock and a number that moves when retrieval breaks are.

SUT numbers come from Relaydesk `npx --yes tsx eval/bench.ts` (2026-08-28). Evaluator numbers come from `uv run python scripts/bench_evaluators.py` on [`examples/nimbus/baseline.json`](../examples/nimbus/baseline.json).

## System under test (40 questions)

| Path | mean ms/row | p95 ms | tokens/row | $ / 40 rows |
| --- | --- | --- | --- | --- |
| Extractive `POST /api/eval` | 0.122 | 0.165 | 0 | 0 |
| LangGraph, no key | 1.622 | 4.194 | 0 | 0 |
| LLM generate+rewrite (estimate) | unmeasured | unmeasured | 727 | 0.00706 |

Extractive is `retrieve` + `extractiveAnswer` in-process, the same work as `/api/eval`. 9 of 40 rows would rewrite (`top_score` under 6). LLM $ uses gpt-4o-mini **$0.15 / $0.60 per 1M** and chars/4. LLM p95 was not measured. There is no API key here. That p95 would be the model HTTP round trip.

## Evaluators (no SUT)

| Evaluator | n | wall ms | ms/row | context_recall | context_precision |
| --- | --- | --- | --- | --- | --- |
| stub | 40 | 0.6 | 0.02 | 0.7824 | 0.7515 |
| lexical | 40 | 1.6 | 0.04 | 0.8799 | 0.0634 |
| ragas live, 10 rows | skipped | | | | `OPENAI_API_KEY` unset |
| ragas token floor, 10 rows | | | | | $0.0056 |
| ragas token floor, 40 rows | | | | | $0.0210 |

RAGAS floor is 5 gpt-4o-mini passes over question+answer+contexts. Live faithfulness splits statements, so expect more. The wrapper awaits each metric per row.

Snapshot: [`evaluator-bench.json`](../examples/nimbus/evaluator-bench.json). Relaydesk write-up: `eval/cost.md` in that repo.

## Why lexical stays

Stub says context precision is **0.75**. Lexical says **0.063** on the same rows. Stub hashes. It will not fail when you cut `k` from 3 to 1. Lexical did. See [nimbus-case-study.md](nimbus-case-study.md).

Do not fail CI on dollars. **$0.02** a PR is fine. Fail it when mean context recall drops more than 0.05. Keep RAGAS off the default job: it needs a key, it is not reproducible, and it leaves the millisecond budget.
