from __future__ import annotations

import operator
from dataclasses import dataclass, field
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send
from pydantic_ai.models import Model

from rag_eval_harness.agent.agents import Finding, Summary, diagnose, summarize
from rag_eval_harness.agent.triage import STAGE_ORDER, FailureGroup, triage
from rag_eval_harness.regression.compare import RegressionReport
from rag_eval_harness.types import RowScore


class InvestigationState(TypedDict, total=False):
    report: RegressionReport
    baseline_rows: list[RowScore]
    head_rows: list[RowScore]
    limit: int
    groups: list[FailureGroup]
    findings: Annotated[list[Finding], operator.add]
    summary: Summary


class DiagnoseTask(TypedDict):
    group: FailureGroup


def _by_stage(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda finding: STAGE_ORDER.index(finding.group.stage))


def build_graph(model: Model | str):
    """triage -> one diagnose per failing stage, in parallel -> summarize."""

    def triage_node(state: InvestigationState) -> dict[str, Any]:
        groups = triage(
            state["report"], state["baseline_rows"], state["head_rows"], limit=state["limit"]
        )
        return {"groups": groups}

    def fan_out(state: InvestigationState) -> list[Send] | str:
        if not state["groups"]:
            return END
        return [Send("diagnose", {"group": group}) for group in state["groups"]]

    async def diagnose_node(task: DiagnoseTask) -> dict[str, Any]:
        diagnosis = await diagnose(task["group"], model=model)
        return {"findings": [Finding(task["group"], diagnosis)]}

    async def summarize_node(state: InvestigationState) -> dict[str, Any]:
        summary = await summarize(state["report"], _by_stage(state["findings"]), model=model)
        return {"summary": summary}

    graph = StateGraph(InvestigationState)
    graph.add_node("triage", triage_node)
    graph.add_node("diagnose", diagnose_node)
    graph.add_node("summarize", summarize_node)
    graph.add_edge(START, "triage")
    graph.add_conditional_edges("triage", fan_out, ["diagnose", END])
    graph.add_edge("diagnose", "summarize")
    graph.add_edge("summarize", END)
    return graph.compile()


@dataclass
class Investigation:
    report: RegressionReport
    findings: list[Finding] = field(default_factory=list)
    summary: Summary | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "report": self.report.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "summary": self.summary.model_dump() if self.summary else None,
        }

    def to_markdown(self) -> str:
        if self.report.passed:
            return "No regression. Nothing to investigate."
        if not self.findings or self.summary is None:
            return (
                "The gate failed, but no row dropped on the failing metrics. "
                "Check row errors with `rag-eval diff`."
            )
        lines = ["## Why the gate failed", "", self.summary.headline, "", self.summary.likely_cause]
        for finding in self.findings:
            group, diagnosis = finding.group, finding.diagnosis
            metrics = ", ".join(
                f"{item.metric} {item.baseline:.3f} -> {item.head:.3f}" for item in group.metrics
            )
            questions = {row.index: row.question for row in group.rows}
            lines += [
                "",
                f"### {group.stage}: {metrics}",
                "",
                f"{diagnosis.suspected_cause} (confidence: {diagnosis.confidence})",
                "",
                f"Try: {diagnosis.suggested_fix}",
            ]
            if diagnosis.evidence_rows:
                lines += ["", "Evidence:"]
                lines += [f"- [{index}] {questions[index]}" for index in diagnosis.evidence_rows]
        if self.summary.next_steps:
            lines += ["", "### Next steps", ""]
            lines += [f"{n}. {step}" for n, step in enumerate(self.summary.next_steps, start=1)]
        return "\n".join(lines)


async def investigate(
    report: RegressionReport,
    baseline_rows: list[RowScore],
    head_rows: list[RowScore],
    *,
    model: Model | str,
    limit: int = 5,
) -> Investigation:
    """Explain a failed gate. A passing report returns without calling a model."""
    if report.passed:
        return Investigation(report=report)
    state = await build_graph(model).ainvoke(
        {
            "report": report,
            "baseline_rows": baseline_rows,
            "head_rows": head_rows,
            "limit": limit,
            "findings": [],
        }
    )
    return Investigation(
        report=report,
        findings=_by_stage(state.get("findings", [])),
        summary=state.get("summary"),
    )
