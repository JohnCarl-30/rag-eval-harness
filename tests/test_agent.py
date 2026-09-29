from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pydantic_ai")
pytest.importorskip("langgraph")

from pydantic_ai import ModelResponse, ToolCallPart, models  # noqa: E402
from pydantic_ai.messages import ModelRequest  # noqa: E402
from pydantic_ai.models.function import AgentInfo, FunctionModel  # noqa: E402
from typer.testing import CliRunner  # noqa: E402

from rag_eval_harness.agent.agents import diagnoser, synthesizer  # noqa: E402
from rag_eval_harness.agent.graph import investigate  # noqa: E402
from rag_eval_harness.cli import app  # noqa: E402
from rag_eval_harness.regression.compare import (  # noqa: E402
    compare_means,
    load_means_ref,
    load_rows_ref,
)
from rag_eval_harness.types import RowScore, compute_means  # noqa: E402

NIMBUS = Path(__file__).resolve().parents[1] / "examples" / "nimbus"
runner = CliRunner()


@pytest.fixture(autouse=True)
def _no_real_models(monkeypatch) -> None:
    monkeypatch.setattr(models, "ALLOW_MODEL_REQUESTS", False)


def _prompt_text(messages: list) -> str:
    return "\n".join(
        str(getattr(part, "content", ""))
        for message in messages
        if isinstance(message, ModelRequest)
        for part in message.parts
    )


class FakeModel:
    """Answers the diagnoser and the synthesizer by the output schema they ask for."""

    def __init__(self, diagnoses: list[dict] | None = None) -> None:
        self.diagnoses = list(diagnoses or [])
        self.diagnoser_prompts: list[str] = []
        self.synthesizer_prompts: list[str] = []
        self.model = FunctionModel(self._respond)

    def _respond(self, messages: list, info: AgentInfo) -> ModelResponse:
        tool = info.output_tools[0]
        prompt = _prompt_text(messages)
        if "suspected_cause" in tool.parameters_json_schema["properties"]:
            self.diagnoser_prompts.append(prompt)
            args = self.diagnoses.pop(0) if self.diagnoses else _diagnosis([])
        else:
            self.synthesizer_prompts.append(prompt)
            args = {
                "headline": "Recall fell because the retriever returns fewer articles.",
                "likely_cause": "Head drops the second article for most questions.",
                "next_steps": ["Restore top_k=3", "Re-run the Nimbus gate"],
            }
        return ModelResponse(parts=[ToolCallPart(tool.name, args)])


def _diagnosis(rows: list[int]) -> dict:
    return {
        "suspected_cause": "Head returns one article where baseline returned two.",
        "evidence_rows": rows,
        "suggested_fix": "Raise top_k back to the baseline value.",
        "confidence": "medium",
    }


def _nimbus(head: str):
    _, b_means = load_means_ref(str(NIMBUS / "baseline.json"))
    _, h_means = load_means_ref(str(NIMBUS / f"{head}.json"))
    _, b_rows = load_rows_ref(str(NIMBUS / "baseline.json"))
    _, h_rows = load_rows_ref(str(NIMBUS / f"{head}.json"))
    return compare_means(b_means, h_means, threshold=0.05), b_rows, h_rows


async def test_investigate_nimbus_weak() -> None:
    fake = FakeModel([_diagnosis([31, 21])])
    report, b_rows, h_rows = _nimbus("weak")

    result = await investigate(report, b_rows, h_rows, model=fake.model)

    assert [finding.group.stage for finding in result.findings] == ["retrieval"]
    assert result.findings[0].diagnosis.evidence_rows == [31, 21]
    assert len(fake.diagnoser_prompts) == 1
    prompt = fake.diagnoser_prompts[0]
    assert "When does Export CSV email a link instead of downloading?" in prompt
    assert "Lost contexts:" in prompt
    assert "context_recall: 0.880 -> 0.740" in prompt
    assert "Evidence rows: [31, 21]" in fake.synthesizer_prompts[0]
    markdown = result.to_markdown()
    assert "## Why the gate failed" in markdown
    assert "### retrieval: context_recall 0.880 -> 0.740" in markdown
    assert "- [31] When does Export CSV email a link instead of downloading?" in markdown
    assert "1. Restore top_k=3" in markdown
    assert json.loads(json.dumps(result.to_dict()))["findings"][0]["stage"] == "retrieval"


async def test_diagnoser_retries_when_citing_unknown_rows() -> None:
    fake = FakeModel([_diagnosis([999]), _diagnosis([31])])
    report, b_rows, h_rows = _nimbus("weak")

    result = await investigate(report, b_rows, h_rows, model=fake.model)

    assert len(fake.diagnoser_prompts) == 2
    assert "Rows [999] are not in this group" in fake.diagnoser_prompts[1]
    assert result.findings[0].diagnosis.evidence_rows == [31]


async def test_passing_report_calls_no_model() -> None:
    fake = FakeModel()
    report, b_rows, _ = _nimbus("baseline")

    result = await investigate(report, b_rows, b_rows, model=fake.model)

    assert result.findings == []
    assert fake.diagnoser_prompts == []
    assert fake.synthesizer_prompts == []
    assert result.to_markdown() == "No regression. Nothing to investigate."


async def test_one_diagnoser_per_failing_stage() -> None:
    def row(question: str, recall: float, faith: float) -> RowScore:
        return RowScore(
            question=question,
            answer="a",
            retrieved_contexts=["c"],
            ground_truth="t",
            metrics={"context_recall": recall, "faithfulness": faith},
        )

    baseline = [row("q0", 1.0, 1.0), row("q1", 1.0, 1.0), row("q2", 1.0, 1.0)]
    head = [row("q0", 0.0, 1.0), row("q1", 1.0, 0.0), row("q2", 1.0, 1.0)]
    report = compare_means(compute_means(baseline), compute_means(head), threshold=0.05)
    fake = FakeModel()

    result = await investigate(report, baseline, head, model=fake.model)

    assert [finding.group.stage for finding in result.findings] == ["retrieval", "generation"]
    assert len(fake.diagnoser_prompts) == 2
    assert len(fake.synthesizer_prompts) == 1


def test_cli_investigate_explains_and_exits_1(tmp_path) -> None:
    fake = FakeModel([_diagnosis([31])])
    out = tmp_path / "investigation.json"
    with diagnoser.override(model=fake.model), synthesizer.override(model=fake.model):
        result = runner.invoke(
            app,
            [
                "investigate",
                "--baseline",
                str(NIMBUS / "baseline.json"),
                "--head",
                str(NIMBUS / "weak.json"),
                "-o",
                str(out),
            ],
        )
    assert result.exit_code == 1, result.output
    assert "context_recall" in result.output and "FAIL" in result.output
    assert "## Why the gate failed" in result.output
    assert "Regression detected." in result.output
    assert json.loads(out.read_text())["summary"]["next_steps"][0] == "Restore top_k=3"


def test_cli_investigate_passing_skips_agents() -> None:
    result = runner.invoke(
        app,
        [
            "investigate",
            "--baseline",
            str(NIMBUS / "baseline.json"),
            "--head",
            str(NIMBUS / "baseline.json"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "Nothing to investigate." in result.output


def test_cli_investigate_model_failure_still_exits_1(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = runner.invoke(
        app,
        [
            "investigate",
            "--baseline",
            str(NIMBUS / "baseline.json"),
            "--head",
            str(NIMBUS / "weak.json"),
            "--model",
            "openai-chat:gpt-4o-mini",
        ],
    )
    assert result.exit_code == 1, result.output
    assert "Investigation failed:" in result.output
    assert "Regression detected." in result.output


def test_cli_investigate_report_includes_explanation(tmp_path) -> None:
    fake = FakeModel([_diagnosis([31])])
    out = tmp_path / "report.md"
    with diagnoser.override(model=fake.model), synthesizer.override(model=fake.model):
        result = runner.invoke(
            app,
            [
                "investigate",
                "--baseline",
                str(NIMBUS / "baseline.json"),
                "--head",
                str(NIMBUS / "weak.json"),
                "--report",
                str(out),
            ],
        )
    assert result.exit_code == 1, result.output
    text = out.read_text()
    assert text.startswith("### rag-eval: ❌ Regression detected")
    assert "### Why the gate failed" in text
    assert "- [31] When does Export CSV email a link instead of downloading?" in text


def test_cli_investigate_report_survives_model_failure(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        [
            "investigate",
            "--baseline",
            str(NIMBUS / "baseline.json"),
            "--head",
            str(NIMBUS / "weak.json"),
            "--model",
            "openai-chat:gpt-4o-mini",
            "--report",
            str(out),
        ],
    )
    assert result.exit_code == 1, result.output
    text = out.read_text()
    assert "**FAIL**" in text
    assert "Investigation failed: `UserError`." in text
