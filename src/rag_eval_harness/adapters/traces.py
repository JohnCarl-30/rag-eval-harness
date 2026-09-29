from __future__ import annotations

from rag_eval_harness.types import EvalRow


class TracesAdapter:
    """Use precomputed answers and retrieved contexts already on each row."""

    name = "traces"

    def run(self, rows: list[EvalRow]) -> list[EvalRow]:
        out: list[EvalRow] = []
        for row in rows:
            if row.error:
                out.append(row)
                continue
            if row.answer is None or not str(row.answer).strip():
                out.append(
                    EvalRow(
                        question=row.question,
                        answer=row.answer,
                        retrieved_contexts=row.retrieved_contexts,
                        ground_truth=row.ground_truth,
                        error="missing answer for traces adapter",
                        abstained=row.abstained,
                        reference_contexts=row.reference_contexts,
                    )
                )
                continue
            out.append(row)
        return out
