from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import pydantic_ai
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimits
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage

from rag_eval_harness.agent.trace import TraceRecorder
from rag_eval_harness.agent.triage import FailureGroup, RowEvidence
from rag_eval_harness.regression.compare import RegressionReport

# The CLI prints to a terminal and to CI logs. Pydantic AI's first-run banner would land in both.
pydantic_ai.BANNER_ENABLED = False

USAGE_LIMITS = UsageLimits(request_limit=4)

METRIC_GLOSSARY = """\
Metrics (0 to 1, higher is better; scores come from an LLM judge or from token overlap):
- context_recall: how much of the ground truth the retrieved contexts support.
- context_precision: how much of the retrieved context is relevant to the ground truth.
- faithfulness: how much of the answer the retrieved contexts support.
- answer_relevancy: how directly the answer addresses the question."""

DIAGNOSER_INSTRUCTIONS = f"""\
You diagnose one stage of a RAG regression. The same questions ran through a baseline
pipeline and a head pipeline. Mean scores for this stage dropped past the CI threshold.

You get the rows that dropped most. For each row: the question, the ground truth, both
answers, the contexts the baseline retrieved that the head did not ("lost"), and the
contexts the head retrieved that the baseline did not ("gained").

Name the one change in the pipeline that best explains the drop across rows, such as
fewer results returned, a different chunk size, a different ranker, or a prompt change.
Cite only the row indexes you were given. If the rows do not support a single cause, say
so and set confidence to low. Do not invent pipeline details the evidence does not show.

{METRIC_GLOSSARY}"""

SYNTHESIZER_INSTRUCTIONS = """\
You write the explanation attached to a failed RAG regression gate. You get the mean
metric table and one diagnosis per failing pipeline stage. Write for an engineer reading
a CI log: plain words, no hedging beyond what the diagnoses state, no new causes."""


class Diagnosis(BaseModel):
    suspected_cause: str = Field(description="One or two sentences naming what changed.")
    evidence_rows: list[int] = Field(description="Row indexes from the prompt that show it.")
    suggested_fix: str = Field(description="One concrete change to try next.")
    confidence: Literal["low", "medium", "high"]


class Summary(BaseModel):
    headline: str = Field(description="One sentence a reviewer reads first.")
    likely_cause: str = Field(description="The cause, in two sentences at most.")
    next_steps: list[str] = Field(description="At most three, most useful first.")


@dataclass
class Finding:
    group: FailureGroup
    diagnosis: Diagnosis

    def to_dict(self) -> dict[str, Any]:
        return {**self.group.to_dict(), "diagnosis": self.diagnosis.model_dump()}


diagnoser = Agent(
    output_type=Diagnosis,
    deps_type=FailureGroup,
    instructions=DIAGNOSER_INSTRUCTIONS,
    name="diagnoser",
)

synthesizer = Agent(
    output_type=Summary,
    instructions=SYNTHESIZER_INSTRUCTIONS,
    name="synthesizer",
)


@diagnoser.output_validator
def _cites_known_rows(ctx: RunContext[FailureGroup], output: Diagnosis) -> Diagnosis:
    known = {row.index for row in ctx.deps.rows}
    unknown = sorted(set(output.evidence_rows) - known)
    if unknown:
        raise ModelRetry(f"Rows {unknown} are not in this group. Cite only {sorted(known)}.")
    return output


def _render_contexts(label: str, contexts: list[str]) -> list[str]:
    if not contexts:
        return [f"{label}: none"]
    return [f"{label}:"] + [f"  - {text}" for text in contexts]


def _render_row(row: RowEvidence) -> str:
    drops = ", ".join(
        f"{name} {before:.3f} -> {after:.3f}" for name, (before, after) in row.drops.items()
    )
    lines = [
        f"### Row {row.index}",
        f"Question: {row.question}",
        f"Ground truth: {row.ground_truth or '(none)'}",
        f"Drops: {drops}",
        f"Baseline answer: {row.baseline_answer or '(none)'}",
        f"Head answer: {row.head_answer or '(none)'}",
        *_render_contexts("Lost contexts", row.lost_contexts),
        *_render_contexts("Gained contexts", row.gained_contexts),
    ]
    return "\n".join(lines)


def render_group(group: FailureGroup) -> str:
    metrics = "\n".join(
        f"- {item.metric}: {item.baseline:.3f} -> {item.head:.3f} ({item.delta:+.3f})"
        for item in group.metrics
    )
    rows = "\n\n".join(_render_row(row) for row in group.rows)
    return f"Stage: {group.stage}\n\nFailing means:\n{metrics}\n\n{rows}"


def render_findings(report: RegressionReport, findings: list[Finding]) -> str:
    table = "\n".join(
        f"- {item.metric}: {item.baseline:.3f} -> {item.head:.3f} ({item.delta:+.3f})"
        f"{'  FAIL' if item.dropped else ''}"
        for item in report.deltas
    )
    parts = [f"Threshold: {report.threshold}\n\nMeans:\n{table}"]
    for finding in findings:
        diagnosis = finding.diagnosis
        parts.append(
            f"## {finding.group.stage} diagnosis ({diagnosis.confidence} confidence)\n"
            f"Cause: {diagnosis.suspected_cause}\n"
            f"Evidence rows: {diagnosis.evidence_rows}\n"
            f"Suggested fix: {diagnosis.suggested_fix}"
        )
    return "\n\n".join(parts)


async def diagnose(
    group: FailureGroup,
    *,
    model: Model | str,
    recorder: TraceRecorder | None = None,
    usage: RunUsage | None = None,
    usage_limits: UsageLimits | None = USAGE_LIMITS,
) -> Diagnosis:
    """Run the diagnoser. A delegating agent passes its own usage so one budget covers both."""
    recorder = recorder or TraceRecorder()
    start = TraceRecorder.counts(usage)
    async with recorder.span("diagnoser", stage=group.stage, delegated=usage is not None) as entry:
        result = await diagnoser.run(
            render_group(group),
            deps=group,
            model=model,
            usage=usage,
            usage_limits=usage_limits,
        )
        recorder.finish(entry, result, start=start)
    return result.output


async def summarize(
    report: RegressionReport,
    findings: list[Finding],
    *,
    model: Model | str,
    recorder: TraceRecorder | None = None,
) -> Summary:
    recorder = recorder or TraceRecorder()
    async with recorder.span("synthesizer") as entry:
        result = await synthesizer.run(
            render_findings(report, findings), model=model, usage_limits=USAGE_LIMITS
        )
        recorder.finish(entry, result)
    return result.output
