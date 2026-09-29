from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from rag_eval_harness.cli import app
from rag_eval_harness.regression.compare import compare_means
from rag_eval_harness.regression.markdown import gate_markdown

NIMBUS = Path(__file__).resolve().parents[1] / "examples" / "nimbus"
runner = CliRunner()


def test_gate_markdown_marks_failures_and_errors() -> None:
    report = compare_means(
        {"context_recall": 0.88, "faithfulness": 0.78},
        {"context_recall": 0.74, "faithfulness": 0.77},
        baseline_ref="base.json",
        head_ref="head.json",
        baseline_errors=0,
        head_errors=2,
    )

    text = gate_markdown(report, explanation="### Why the gate failed\n\nFewer articles.")

    assert text.startswith("### rag-eval: ❌ Regression detected")
    assert "| context_recall | 0.8800 | 0.7400 | -0.1400 | **FAIL** |" in text
    assert "| faithfulness | 0.7800 | 0.7700 | -0.0100 | ok |" in text
    assert "| errored rows | 0 | 2 | | **FAIL** |" in text
    assert text.rstrip().endswith("Fewer articles.")


def test_gate_markdown_passing() -> None:
    report = compare_means({"mrr": 0.8}, {"mrr": 0.8})
    assert gate_markdown(report).startswith("### rag-eval: ✅ No regression")


def test_regress_writes_report_and_keeps_exit_code(tmp_path) -> None:
    out = tmp_path / "report.md"
    result = runner.invoke(
        app,
        [
            "regress",
            "--baseline",
            str(NIMBUS / "baseline.json"),
            "--head",
            str(NIMBUS / "weak.json"),
            "--report",
            str(out),
        ],
    )
    assert result.exit_code == 1, result.output
    assert "| context_recall | 0.8799 | 0.7399 | -0.1399 | **FAIL** |" in out.read_text()
