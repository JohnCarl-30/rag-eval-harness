# Regression investigator

`rag-eval regress` says *that* a mean dropped. `rag-eval investigate` runs the same gate, then has agents explain *why*.

```bash
pip install 'rag-eval-harness[agent]'      # or: uv sync --extra agent
rag-eval investigate \
  --baseline examples/nimbus/baseline.json \
  --head examples/nimbus/weak.json \
  -o investigation.json
```

The exit code is the gate's, never the model's: 0 on a pass, 1 on a regression, 2 on bad input. A pass calls no model. A failed model call prints `Investigation failed: …` and still exits 1.

## Two modes

LangGraph owns the control flow. Pydantic AI owns each model call, its tools, and its typed output. Both modes are paths in one graph, picked at `START`.

```
        ┌─ workflow ──→ triage ─┬─ diagnose (retrieval)  ─┬─ summarize → END
START ──┤                       └─ diagnose (generation) ─┘
        └─ supervisor → supervise (tool loop, delegates to diagnose) → END
```

### `--mode workflow` (default)

A fixed orchestrator–workers graph. Use it in CI: the steps and the model-call count are known in advance.

| Node | What it does | Model |
| --- | --- | --- |
| `triage` | Groups failing means by stage (`context_*` → retrieval, `faithfulness` / `answer_relevancy` → generation, anything else → other). Attaches the `--limit` worst rows per group, with the contexts the head lost and gained versus baseline. | none |
| `diagnose` | One per group, in parallel via `Send`. Returns a `Diagnosis`: cause, cited rows, fix, confidence. An output validator rejects row indexes the group does not contain and asks the model to retry. | yes |
| `summarize` | Reads the mean table and every diagnosis. Returns a `Summary`: headline, cause, up to three next steps. | yes |

### `--mode supervisor`

One Pydantic AI agent decides what to look at. It has four tools, all read-only over the two runs:

| Tool | Returns |
| --- | --- |
| `failing_metrics` | Every mean, its stage, and whether it failed |
| `worst_rows(metric, limit)` | Rows that dropped most on one metric (max 10) |
| `row_detail(index)` | Question, ground truth, scores, both answers, lost and gained contexts |
| `diagnose_stage(stage)` | Delegates the stage to the `diagnose` agent above and returns its `Diagnosis` |

Bad arguments (an unknown metric, a row that does not exist, a stage with no failing rows) raise `ModelRetry`, so the model sees the error and tries again. The supervisor and every diagnoser it calls share one budget: 15 model requests and 20 tool calls. Past that, the run stops with `UsageLimitExceeded` and the command exits 1.

Use it to explore a failure by hand. It costs more and varies more run to run than the workflow.

Rows pair by index in both modes, as in `rag-eval diff`.

## Model

`--model` takes any Pydantic AI model string (`provider:model`). Without it, the command uses `openai-chat:$OPENAI_MODEL` (default `gpt-4o-mini`), so a key that already runs the `ragas` evaluator works here too. `openai-chat:` uses Chat Completions, which OpenAI-compatible servers behind `OPENAI_BASE_URL` also speak.

```bash
export RAG_EVAL_AGENT_MODEL=anthropic:claude-sonnet-5   # needs ANTHROPIC_API_KEY
```

The workflow caps each agent run at 4 model requests. A Nimbus-sized failure with one failing stage is two agent runs.

## Tracing

`--trace trace.json` writes every agent run, including on failure:

```json
{
  "runs": [
    {"agent": "diagnoser", "stage": "retrieval", "delegated": true,
     "usage": {"requests": 1, "input_tokens": 2100, "output_tokens": 90},
     "duration_ms": 1830.4, "messages": ["…prompts, tool calls, tool returns, outputs…"]},
    {"agent": "supervisor", "delegated": false,
     "usage": {"requests": 6, "input_tokens": 9800, "output_tokens": 420},
     "duration_ms": 7412.9, "messages": ["…"]}
  ],
  "totals": {"requests": 6, "input_tokens": 9800, "output_tokens": 420}
}
```

A delegated run records only its own usage. Its parent's usage already includes it, so `totals` counts top-level runs only. A run that raised has an `error` field.

`--otel` sends live spans through [Logfire](https://github.com/pydantic/logfire) instead. It needs `pip install 'rag-eval-harness[trace]'`. With `LOGFIRE_TOKEN` set, spans go to Logfire. Without it, set the standard `OTEL_EXPORTER_OTLP_ENDPOINT` to send to any OpenTelemetry backend (Jaeger, Grafana Tempo, Honeycomb).

## What leaves the machine

For each failing stage, up to `--limit` rows go to the model provider: question, ground truth, both answers, and the lost and gained contexts, each clipped to 800 characters. In supervisor mode, the model asks for rows itself, up to the tool-call budget. `--otel` spans include prompts and responses, so the same text also goes to the tracing backend. `regress` and `diff` send nothing.

## Tests

`tests/test_agent.py` and `tests/test_supervisor.py` drive both modes with Pydantic AI's `FunctionModel` and set `ALLOW_MODEL_REQUESTS = False`, so CI needs no key. The supervisor tests script the tool calls and check what each tool returned. `tests/test_triage.py` needs no extra.
