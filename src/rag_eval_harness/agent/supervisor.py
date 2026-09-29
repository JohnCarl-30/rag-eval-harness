from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import Agent, ModelRetry, RunContext, UsageLimits
from pydantic_ai.models import Model

from rag_eval_harness.agent.agents import METRIC_GLOSSARY, Finding, Summary, diagnose
from rag_eval_harness.agent.trace import TraceRecorder
from rag_eval_harness.agent.triage import STAGE_BY_METRIC, Stage, row_evidence, triage
from rag_eval_harness.regression.compare import RegressionReport, worst_row_drops
from rag_eval_harness.types import RowScore

# One budget for the supervisor and every diagnoser it delegates to.
SUPERVISOR_LIMITS = UsageLimits(request_limit=15, tool_calls_limit=20)
MAX_WORST_ROWS = 10

SUPERVISOR_INSTRUCTIONS = f"""\
You investigate a failed RAG regression gate. The same questions ran through a baseline
pipeline and a head pipeline, and at least one mean metric dropped past the threshold.

Use the tools to find out why. Start with failing_metrics. Look at the worst rows for each
failing metric and open a few with row_detail. Call diagnose_stage for a failing stage
when you want a careful diagnosis of its rows. Stop once the evidence supports a cause.
Do not invent pipeline details the tools did not show.

{METRIC_GLOSSARY}"""


@dataclass
class SupervisorDeps:
    report: RegressionReport
    baseline_rows: list[RowScore]
    head_rows: list[RowScore]
    model: Model | str
    limit: int
    recorder: TraceRecorder
    findings: list[Finding] = field(default_factory=list)


supervisor = Agent(
    output_type=Summary,
    deps_type=SupervisorDeps,
    instructions=SUPERVISOR_INSTRUCTIONS,
    name="supervisor",
)


@supervisor.tool
def failing_metrics(ctx: RunContext[SupervisorDeps]) -> list[dict[str, Any]]:
    """Mean of every metric for baseline and head, its pipeline stage, and whether it failed."""
    return [
        {
            "metric": item.metric,
            "stage": STAGE_BY_METRIC.get(item.metric, "other"),
            "baseline": round(item.baseline, 4),
            "head": round(item.head, 4),
            "delta": round(item.delta, 4),
            "failed": item.dropped,
        }
        for item in ctx.deps.report.deltas
    ]


@supervisor.tool
def worst_rows(
    ctx: RunContext[SupervisorDeps], metric: str, limit: int = 5
) -> list[dict[str, Any]]:
    """Rows whose score on `metric` dropped most from baseline to head, worst first."""
    known = sorted(item.metric for item in ctx.deps.report.deltas)
    if metric not in known:
        raise ModelRetry(f"Unknown metric {metric!r}. Use one of {known}.")
    drops = worst_row_drops(
        ctx.deps.baseline_rows,
        ctx.deps.head_rows,
        metric=metric,
        limit=min(max(limit, 1), MAX_WORST_ROWS),
    )
    return [
        {
            "index": item.index,
            "question": item.question,
            "baseline": round(item.baseline, 4),
            "head": round(item.head, 4),
        }
        for item in drops
    ]


@supervisor.tool
def row_detail(ctx: RunContext[SupervisorDeps], index: int) -> dict[str, Any]:
    """One row: question, ground truth, scores, both answers, and contexts head lost or gained."""
    baseline, head = ctx.deps.baseline_rows, ctx.deps.head_rows
    count = min(len(baseline), len(head))
    if not 0 <= index < count:
        raise ModelRetry(f"Row {index} does not exist. Use 0 to {count - 1}.")
    left, right = baseline[index], head[index]
    scores = {
        name: (left.metrics[name], right.metrics[name])
        for name in sorted(set(left.metrics) & set(right.metrics))
    }
    evidence = row_evidence(index, left, right, scores)
    return {
        "index": index,
        "question": evidence.question,
        "ground_truth": evidence.ground_truth,
        "scores": {name: {"baseline": b, "head": h} for name, (b, h) in scores.items()},
        "baseline_answer": evidence.baseline_answer,
        "head_answer": evidence.head_answer,
        "lost_contexts": evidence.lost_contexts,
        "gained_contexts": evidence.gained_contexts,
    }


@supervisor.tool
async def diagnose_stage(ctx: RunContext[SupervisorDeps], stage: Stage) -> dict[str, Any]:
    """Hand one failing stage to the diagnoser agent. Returns cause, cited rows, fix, confidence."""
    deps = ctx.deps
    for finding in deps.findings:
        if finding.group.stage == stage:
            return finding.diagnosis.model_dump()
    groups = {
        group.stage: group
        for group in triage(deps.report, deps.baseline_rows, deps.head_rows, limit=deps.limit)
    }
    group = groups.get(stage)
    if group is None:
        raise ModelRetry(f"Stage {stage!r} has no failing rows. Failing stages: {sorted(groups)}.")
    diagnosis = await diagnose(
        group,
        model=deps.model,
        recorder=deps.recorder,
        usage=ctx.usage,
        usage_limits=ctx.usage_limits,
    )
    deps.findings.append(Finding(group, diagnosis))
    return diagnosis.model_dump()


async def supervise(
    report: RegressionReport,
    baseline_rows: list[RowScore],
    head_rows: list[RowScore],
    *,
    model: Model | str,
    limit: int,
    recorder: TraceRecorder,
) -> tuple[Summary, list[Finding]]:
    deps = SupervisorDeps(
        report=report,
        baseline_rows=baseline_rows,
        head_rows=head_rows,
        model=model,
        limit=limit,
        recorder=recorder,
    )
    async with recorder.span("supervisor") as entry:
        result = await supervisor.run(
            f"The gate failed at threshold {report.threshold}. Find out why.",
            deps=deps,
            model=model,
            usage_limits=SUPERVISOR_LIMITS,
        )
        recorder.finish(entry, result)
    return result.output, deps.findings
