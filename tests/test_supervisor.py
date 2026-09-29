from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")
pytest.importorskip("langgraph")

from pydantic_ai import ModelResponse, ToolCallPart, models  # noqa: E402
from pydantic_ai.exceptions import UsageLimitExceeded  # noqa: E402
from pydantic_ai.messages import (  # noqa: E402
    ModelRequest,
    RetryPromptPart,
    ToolReturnPart,
)
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from rag_eval_harness.agent.agents import diagnoser, synthesizer  # noqa: E402
from rag_eval_harness.agent.graph import investigate  # noqa: E402
from rag_eval_harness.agent.supervisor import supervisor  # noqa: E402
from rag_eval_harness.agent.trace import TraceRecorder  # noqa: E402
from rag_eval_harness.cli import app  # noqa: E402
from rag_eval_harness.regression.compare import (  # noqa: E402
    compare_means,
    load_means_ref,
    load_rows_ref,
)

NIMBUS = Path(__file__).resolve().parents[1] / "examples" / "nimbus"
runner = CliRunner()

SUMMARY = {
    "headline": "Recall fell because head retrieves fewer articles.",
    "likely_cause": "Head drops articles the baseline retrieved.",
    "next_steps": ["Restore top_k"],
}
DIAGNOSIS = {
    "suspected_cause": "Head returns one article where baseline returned two.",
    "evidence_rows": [31],
    "suggested_fix": "Raise top_k.",
    "confidence": "medium",
}


@pytest.fixture(autouse=True)
def _no_real_models(monkeypatch) -> None:
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)


def _nimbus(head: str = "weak"):
    _, b_means = load_means_ref(str(NIMBUS / "baseline.json"))
    _, h_means = load_means_ref(str(NIMBUS / f"{head}.json"))
    _, b_rows = load_rows_ref(str(NIMBUS / "baseline.json"))
    _, h_rows = load_rows_ref(str(NIMBUS / f"{head}.json"))
    return compare_means(b_means, h_means, threshold=0.05), b_rows, h_rows


class ScriptedModel:
    """Plays the supervisor from a script of tool calls; answers the diagnoser directly."""

    def __init__(self, script: list[tuple[str, dict]], *, loop_tool: bool = False) -> None:
        self.script = script
        self.loop_tool = loop_tool
        self.tool_returns: dict[str, list] = {}
        self.retries: list[str] = []
        self.diagnoser_calls = 0
        self.model = FunctionModel(self._respond)

    def _respond(self, messages: list, info: AgentInfo) -> ModelResponse:
        output = info.output_tools[0]
        if "suspected_cause" in output.parameters_json_schema["properties"]:
            self.diagnoser_calls += 1
            return ModelResponse(parts=[ToolCallPart(output.name, DIAGNOSIS)])
        last = messages[-1]
        if isinstance(last, ModelRequest):
            for part in last.parts:
                if isinstance(part, ToolReturnPart):
                    self.tool_returns.setdefault(part.tool_name, []).append(part.content)
                if isinstance(part, RetryPromptPart):
                    self.retries.append(part.model_response())
        if self.loop_tool:
            return ModelResponse(parts=[ToolCallPart("failing_metrics", {})])
        step = sum(1 for message in messages if not isinstance(message, ModelRequest))
        if step < len(self.script):
            name, args = self.script[step]
            return ModelResponse(parts=[ToolCallPart(name, args)])
        return ModelResponse(parts=[ToolCallPart(output.name, SUMMARY)])


FULL_SCRIPT = [
    ("failing_metrics", {}),
    ("worst_rows", {"metric": "context_recall", "limit": 3}),
    ("row_detail", {"index": 31}),
    ("diagnose_stage", {"stage": "retrieval"}),
]


async def test_supervisor_uses_tools_and_delegates() -> None:
    fake = ScriptedModel(FULL_SCRIPT)
    recorder = TraceRecorder()
    report, b_rows, h_rows = _nimbus()

    result = await investigate(
        report, b_rows, h_rows, model=fake.model, mode="supervisor", recorder=recorder
    )

    metrics = {item["metric"]: item for item in fake.tool_returns["failing_metrics"][0]}
    assert metrics["context_recall"]["failed"] is True
    assert metrics["context_recall"]["stage"] == "retrieval"
    assert fake.tool_returns["worst_rows"][0][0]["index"] == 31
    detail = fake.tool_returns["row_detail"][0]
    assert detail["question"] == "When does Export CSV email a link instead of downloading?"
    assert detail["lost_contexts"] and not detail["gained_contexts"]
    assert fake.tool_returns["diagnose_stage"][0]["evidence_rows"] == [31]
    assert fake.diagnoser_calls == 1

    assert result.mode == "supervisor"
    assert result.summary is not None and result.summary.headline == SUMMARY["headline"]
    assert [finding.group.stage for finding in result.findings] == ["retrieval"]
    assert "### retrieval: context_recall 0.880 -> 0.740" in result.to_markdown()

    runs = {run["agent"]: run for run in recorder.runs}
    assert set(runs) == {"supervisor", "diagnoser"}
    assert runs["diagnoser"]["delegated"] is True
    assert runs["diagnoser"]["usage"]["requests"] == 1
    assert runs["supervisor"]["usage"]["requests"] == 6
    assert recorder.to_dict()["totals"]["requests"] == 6


async def test_supervisor_bad_row_index_retries() -> None:
    fake = ScriptedModel([("row_detail", {"index": 999})])
    report, b_rows, h_rows = _nimbus()

    result = await investigate(report, b_rows, h_rows, model=fake.model, mode="supervisor")

    assert any("Row 999 does not exist" in text for text in fake.retries)
    assert result.summary is not None
    assert result.findings == []


async def test_supervisor_rejects_stage_without_failures() -> None:
    fake = ScriptedModel([("diagnose_stage", {"stage": "generation"})])
    report, b_rows, h_rows = _nimbus()

    await investigate(report, b_rows, h_rows, model=fake.model, mode="supervisor")

    assert any("Stage 'generation' has no failing rows" in text for text in fake.retries)
    assert fake.diagnoser_calls == 0


async def test_supervisor_stops_at_budget() -> None:
    fake = ScriptedModel([], loop_tool=True)
    recorder = TraceRecorder()
    report, b_rows, h_rows = _nimbus()

    with pytest.raises(UsageLimitExceeded):
        await investigate(
            report, b_rows, h_rows, model=fake.model, mode="supervisor", recorder=recorder
        )

    assert recorder.runs[-1]["agent"] == "supervisor"
    assert "UsageLimitExceeded" in recorder.runs[-1]["error"]


async def test_workflow_trace_records_each_agent() -> None:
    fake = ScriptedModel([])
    recorder = TraceRecorder()
    report, b_rows, h_rows = _nimbus()

    await investigate(report, b_rows, h_rows, model=fake.model, recorder=recorder)

    assert [run["agent"] for run in recorder.runs] == ["diagnoser", "synthesizer"]
    assert recorder.runs[0]["stage"] == "retrieval"
    assert recorder.runs[0]["delegated"] is False
    for run in recorder.runs:
        assert run["usage"]["requests"] == 1
        assert run["messages"] and run["duration_ms"] >= 0
    assert recorder.to_dict()["totals"]["requests"] == 2


def test_cli_supervisor_mode_writes_trace(tmp_path) -> None:
    fake = ScriptedModel(FULL_SCRIPT)
    trace = tmp_path / "trace.json"
    with supervisor.override(model=fake.model), diagnoser.override(model=fake.model):
        result = runner.invoke(
            app,
            [
                "investigate",
                "--baseline",
                str(NIMBUS / "baseline.json"),
                "--head",
                str(NIMBUS / "weak.json"),
                "--mode",
                "supervisor",
                "--trace",
                str(trace),
            ],
        )
    assert result.exit_code == 1, result.output
    assert "Investigating (supervisor)" in result.output
    assert "## Why the gate failed" in result.output
    payload = json.loads(trace.read_text())
    assert {run["agent"] for run in payload["runs"]} == {"supervisor", "diagnoser"}


def test_cli_trace_written_when_investigation_fails(tmp_path) -> None:
    fake = ScriptedModel([], loop_tool=True)
    trace = tmp_path / "trace.json"
    with supervisor.override(model=fake.model), synthesizer.override(model=fake.model):
        result = runner.invoke(
            app,
            [
                "investigate",
                "--baseline",
                str(NIMBUS / "baseline.json"),
                "--head",
                str(NIMBUS / "weak.json"),
                "--mode",
                "supervisor",
                "--trace",
                str(trace),
            ],
        )
    assert result.exit_code == 1, result.output
    assert "Investigation failed:" in result.output
    assert "error" in json.loads(trace.read_text())["runs"][-1]


def test_cli_rejects_unknown_mode() -> None:
    result = runner.invoke(
        app,
        [
            "investigate",
            "--baseline",
            str(NIMBUS / "baseline.json"),
            "--head",
            str(NIMBUS / "weak.json"),
            "--mode",
            "swarm",
        ],
    )
    assert result.exit_code == 2
    assert "Unknown --mode 'swarm'" in result.output
