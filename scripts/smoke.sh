#!/usr/bin/env bash
set -euo pipefail

API="${API_URL:-http://127.0.0.1:8000}"
DUMMY="${DUMMY_URL:-http://127.0.0.1:8080}"
KEY="${RAG_EVAL_API_KEY:-dev-key}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

wait_http() {
  local url=$1
  for _ in $(seq 1 60); do
    if curl -fsS "$url" >/dev/null; then
      return 0
    fi
    sleep 2
  done
  echo "timeout waiting for $url" >&2
  return 1
}

wait_http "$API/health"
wait_http "$DUMMY/health"

upload=$(curl -fsS -X POST "$API/api/datasets" \
  -H "X-API-Key: $KEY" \
  -F "file=@$ROOT/examples/dummy-rag/golden.csv")
dataset_id=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$upload")

created=$(curl -fsS -X POST "$API/api/runs" \
  -H "X-API-Key: $KEY" \
  -H "Content-Type: application/json" \
  -d "{\"dataset_id\":\"$dataset_id\",\"adapter\":\"http\",\"evaluator\":\"stub\",\"sut_url\":\"http://dummy-rag:8080/query\",\"label\":\"smoke\"}")
run_id=$(python3 -c "import json,sys; print(json.load(sys.stdin)['id'])" <<<"$created")

for _ in $(seq 1 60); do
  detail=$(curl -fsS "$API/api/runs/$run_id" -H "X-API-Key: $KEY")
  status=$(python3 -c "import json,sys; print(json.load(sys.stdin)['status'])" <<<"$detail")
  if [[ "$status" == "completed" ]]; then
    echo "smoke ok: run $run_id completed"
    echo "$detail" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('means'))"
    exit 0
  fi
  if [[ "$status" == "failed" ]]; then
    echo "run failed: $detail" >&2
    exit 1
  fi
  sleep 2
done

echo "timeout waiting for run $run_id" >&2
exit 1
