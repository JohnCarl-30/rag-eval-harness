#!/usr/bin/env bash
# Fill the RAGAS column for the 15-row Nimbus slice. Needs OPENAI_API_KEY.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -z "${OPENAI_API_KEY:-}" ]]; then
  echo "OPENAI_API_KEY unset. Lexical snapshot is already in examples/nimbus/slice-15-lexical.json" >&2
  echo "See docs/nimbus-judge.md" >&2
  exit 2
fi

uv run rag-eval eval examples/nimbus/slice-15.jsonl \
  --evaluator ragas --label nimbus-slice15-ragas \
  -o examples/nimbus/slice-15-ragas.json

uv run rag-eval diff \
  --baseline examples/nimbus/slice-15-lexical.json \
  --head examples/nimbus/slice-15-ragas.json \
  --metric context_recall
