# Adapters

Two ways to produce answers and retrieved contexts. Both feed the same evaluator.

## Column contract

Required:

- `question` (alias `user_input`)

Optional:

- `ground_truth` (alias `reference`) — unlocks context precision and context recall
- `answer` (alias `response`) — required for the traces adapter
- `retrieved_contexts` (alias `contexts`) — JSON list (`["a","b"]`) or delimited with `|` / newlines

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

`response` / `contexts` aliases are accepted. Each row has its own timeout (CLI `--timeout`, API `timeout_seconds`). HTTP 4xx/5xx, timeouts, and malformed JSON become row errors. Those error strings omit the SUT URL, so a query token in `--sut-url` does not land in the store.

```bash
rag-eval eval golden.csv \
  --sut-url http://127.0.0.1:8080/query \
  --sut-token "$TOKEN" \
  --evaluator stub
```

The dummy FAQ server in `examples/dummy-rag` implements this contract.

JSONPath mapping, agent/tool-call traces, and custom request bodies are out of scope for v1.
