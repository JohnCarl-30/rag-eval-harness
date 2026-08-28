#!/usr/bin/env bash
# 90-second recording: chunking raises precision and fails the recall gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Nimbus case study: paragraph chunks vs article baseline ==="
echo "Expect context_recall to FAIL (0.880 -> 0.782, threshold 0.05)"
echo

set +e
uv run rag-eval regress \
  --baseline examples/nimbus/baseline.json \
  --head examples/nimbus/chunked.json \
  --threshold 0.05
status=$?
set -e

echo
if [[ "$status" -eq 1 ]]; then
  echo "Gate failed as designed. Precision went up. We did not ship the index."
  exit 0
fi
echo "Unexpected: regress exited $status (wanted 1)." >&2
exit "$status"
