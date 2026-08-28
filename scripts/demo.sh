#!/usr/bin/env bash
# 90-second recording: show the Nimbus regression gate going red.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Nimbus case study: weak retriever vs tagged baseline ==="
echo "Expect context_recall to FAIL (0.880 -> 0.740, threshold 0.05)"
echo

set +e
uv run rag-eval regress \
  --baseline examples/nimbus/baseline.json \
  --head examples/nimbus/weak.json \
  --threshold 0.05
status=$?
set -e

echo
if [[ "$status" -eq 1 ]]; then
  echo "Gate failed as designed. That red exit is the product."
  exit 0
fi
echo "Unexpected: regress exited $status (wanted 1)." >&2
exit "$status"
