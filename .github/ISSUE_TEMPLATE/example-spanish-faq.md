---
name: Add a second dummy-rag language
about: Tiny example improvement
title: "good first issue: Spanish FAQ row in dummy-rag"
labels: ["good first issue"]
---

The fixture is English-only besides a language FAQ.

## Task

Add one Spanish question/answer pair to `examples/dummy-rag` (server keywords, `golden.csv`, `traces.jsonl`) without exceeding the 100-row cap.

## Acceptance

- Dummy server still answers the original 15 English questions
- `uv run rag-eval eval examples/dummy-rag/traces.jsonl --evaluator stub` succeeds
