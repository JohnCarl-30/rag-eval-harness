from __future__ import annotations

from rag_eval_harness.regression.compare import RegressionReport


def gate_markdown(report: RegressionReport, *, explanation: str | None = None) -> str:
    """The gate result as GitHub-flavored Markdown: a job summary or a PR comment body."""
    verdict = "❌ Regression detected" if not report.passed else "✅ No regression"
    lines = [
        f"### rag-eval: {verdict}",
        "",
        f"Baseline `{report.baseline_ref}` vs head `{report.head_ref}`, "
        f"threshold {report.threshold}.",
        "",
        "| Metric | Baseline | Head | Delta | |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for item in report.deltas:
        flag = "**FAIL**" if item.dropped else "ok"
        lines.append(
            f"| {item.metric} | {item.baseline:.4f} | {item.head:.4f} "
            f"| {item.delta:+.4f} | {flag} |"
        )
    if report.baseline_errors is not None and report.head_errors is not None:
        flag = "**FAIL**" if report.errors_increased else "ok"
        lines.append(
            f"| errored rows | {report.baseline_errors} | {report.head_errors} | | {flag} |"
        )
    if explanation:
        lines += ["", explanation.strip()]
    return "\n".join(lines) + "\n"
