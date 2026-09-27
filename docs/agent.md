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

## Graph

LangGraph owns the control flow. Pydantic AI owns each model call and its typed output.

```
START → triage ─┬─ diagnose (retrieval)  ─┬─ summarize → END
                └─ diagnose (generation) ─┘
          └──── no row dropped ──────────────→ END
```

| Node | What it does | Model |
| --- | --- | --- |
| `triage` | Groups failing means by stage (`context_*` → retrieval, `faithfulness` / `answer_relevancy` → generation, anything else → other). Attaches the `--limit` worst rows per group, with the contexts the head lost and gained versus baseline. | none |
| `diagnose` | One per group, in parallel via `Send`. Returns a `Diagnosis`: cause, cited rows, fix, confidence. An output validator rejects row indexes the group does not contain and asks the model to retry. | yes |
| `summarize` | Reads the mean table and every diagnosis. Returns a `Summary`: headline, cause, up to three next steps. | yes |

Rows pair by index, as in `rag-eval diff`.

## Model

`--model` takes any Pydantic AI model string (`provider:model`). Without it, the command uses `openai-chat:$OPENAI_MODEL` (default `gpt-4o-mini`), so a key that already runs the `ragas` evaluator works here too. `openai-chat:` uses Chat Completions, which OpenAI-compatible servers behind `OPENAI_BASE_URL` also speak.

```bash
export RAG_EVAL_AGENT_MODEL=anthropic:claude-sonnet-5   # needs ANTHROPIC_API_KEY
```

Each agent run is capped at 4 model requests. A Nimbus-sized failure with one failing stage is two agent runs.

## What leaves the machine

For each failing stage, up to `--limit` rows go to the model provider: question, ground truth, both answers, and the lost and gained contexts, each clipped to 800 characters. `regress` and `diff` send nothing.

## Tests

`tests/test_agent.py` drives the graph with Pydantic AI's `FunctionModel` and sets `ALLOW_MODEL_REQUESTS = False`, so CI needs no key. `tests/test_triage.py` needs no extra.
