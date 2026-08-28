#!/usr/bin/env python3
"""Time stub vs lexical (and ragas if a key is present) on the Nimbus snapshot.

uv run python scripts/bench_evaluators.py
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from rag_eval_harness.evaluators import get_evaluator
from rag_eval_harness.evaluators.ragas import RagasUnavailableError
from rag_eval_harness.types import EvalRow

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "examples" / "nimbus" / "baseline.json"
# gpt-4o-mini list prices, Aug 2026
INPUT_PER_M = 0.15
OUTPUT_PER_M = 0.60
EMBED_PER_M = 0.02


def rows_from_snapshot(path: Path) -> list[EvalRow]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    out: list[EvalRow] = []
    for row in payload["rows"]:
        out.append(
            EvalRow(
                question=row["question"],
                answer=row.get("answer"),
                retrieved_contexts=list(row.get("retrieved_contexts") or []),
                ground_truth=row.get("ground_truth"),
            )
        )
    return out


def time_evaluator(name: str, rows: list[EvalRow]) -> dict:
    evaluator = get_evaluator(name)
    t0 = time.perf_counter()
    summary = evaluator.evaluate(rows)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    return {
        "evaluator": name,
        "n": len(rows),
        "wall_ms": round(elapsed_ms, 1),
        "ms_per_row": round(elapsed_ms / max(len(rows), 1), 2),
        "error_count": summary.error_count,
        "means": {k: round(v, 4) for k, v in summary.means.items()},
    }


def estimate_ragas_usd(rows: list[EvalRow]) -> dict:
    """Floor on judge tokens: 5 LLM passes over question+answer+contexts per row."""
    input_tokens = 0
    output_tokens = 0
    embed_tokens = 0
    for row in rows:
        blob = " ".join(
            [
                row.question,
                row.answer or "",
                row.ground_truth or "",
                *row.retrieved_contexts,
            ]
        )
        ctx = max(1, (len(blob) + 3) // 4)
        # 4 metrics plus one extra faithfulness verify
        input_tokens += ctx * 5
        output_tokens += 80 * 4
        embed_tokens += max(1, len(row.question) // 4) * 4
    usd = (
        input_tokens * INPUT_PER_M + output_tokens * OUTPUT_PER_M + embed_tokens * EMBED_PER_M
    ) / 1e6
    return {
        "n": len(rows),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "embed_tokens": embed_tokens,
        "usd_estimate": round(usd, 6),
        "usd_per_row": round(usd / max(len(rows), 1), 6),
        "note": "floor from context size; live RAGAS is often higher",
    }


def main() -> None:
    rows = rows_from_snapshot(SNAPSHOT)
    slice10 = rows[:10]
    report: dict = {
        "source": str(SNAPSHOT.relative_to(ROOT)),
        "stub_40": time_evaluator("stub", rows),
        "lexical_40": time_evaluator("lexical", rows),
        "stub_10": time_evaluator("stub", slice10),
        "lexical_10": time_evaluator("lexical", slice10),
        "ragas_10_estimate": estimate_ragas_usd(slice10),
        "ragas_40_estimate": estimate_ragas_usd(rows),
    }
    if os.environ.get("OPENAI_API_KEY"):
        try:
            t0 = time.perf_counter()
            live = get_evaluator("ragas").evaluate(slice10)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            report["ragas_10_live"] = {
                "n": 10,
                "wall_ms": round(elapsed_ms, 1),
                "ms_per_row": round(elapsed_ms / 10, 2),
                "error_count": live.error_count,
                "means": {k: round(v, 4) for k, v in live.means.items()},
            }
        except RagasUnavailableError as exc:
            report["ragas_10_live"] = {"skipped": str(exc)}
    else:
        report["ragas_10_live"] = {"skipped": "OPENAI_API_KEY unset"}

    out = ROOT / "examples" / "nimbus" / "evaluator-bench.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
