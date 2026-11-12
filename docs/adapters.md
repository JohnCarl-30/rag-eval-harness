# Adapters

Two ways to produce answers and retrieved contexts. Both feed the same evaluator.

## Column contract

Required:

- `question` (alias `user_input`)

Optional:

- `ground_truth` (alias `reference`) — unlocks context precision and context recall
- `answer` (alias `response`) — required for the traces adapter
- `retrieved_contexts` (alias `contexts`) — JSON list (`["a","b"]`) or delimited with `|` / newlines
- `abstained` (alias `escalated`) — `true` when the pipeline declined to answer; skips answer metrics ([metrics](metrics.md#abstained-rows))

Row cap: **100**. Extra rows are rejected.

## Traces adapter

Use when the pipeline already ran. Point `rag-eval eval` at a CSV/JSONL/JSON file that includes answers:

```bash
rag-eval eval traces.jsonl --evaluator stub
```

A row without an answer is scored as an error; the run continues.

## HTTP adapter

Your RAG must accept:

```http
POST /your-path
Content-Type: application/json
Authorization: Bearer <optional>

{"question": "…"}
```

and respond:

```json
{"answer": "…", "retrieved_contexts": ["…"]}
```

`response` / `contexts` aliases are accepted. Add `"abstained": true` (or `"escalated": true`) when the SUT refused or handed off to a human. Each row has its own timeout (CLI `--timeout`, API `timeout_seconds`). HTTP 4xx/5xx, timeouts, and malformed JSON become row errors. Those error strings omit the SUT URL. The store keeps a redacted adapter config: no bearer token, and the SUT URL without userinfo, query, or fragment. The real URL and token live in memory for the length of the run.

```bash
RAG_EVAL_SUT_TOKEN="$TOKEN" rag-eval eval golden.csv \
  --sut-url http://127.0.0.1:8080/query \
  --evaluator stub
```

`--sut-token` still works. The env var keeps the token out of the process list and shell history.

The dummy FAQ server in `examples/dummy-rag` implements this contract.

JSONPath mapping, agent/tool-call traces, and custom request bodies are out of scope for v1.
