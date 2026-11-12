from __future__ import annotations

from rag_eval_harness.regression.compare import RegressionReport


def row_check_lines(report: RegressionReport) -> list[tuple[str, str, str, bool]]:
    """The gate's row-level checks as (label, baseline, head, failed).

    A check whose counts are unknown is left out. Missing questions only show when
    there are some, so a clean run prints the same table it always did.
    """
    lines: list[tuple[str, str, str, bool]] = []
    if report.baseline_errors is not None and report.head_errors is not None:
        lines.append(
            (
                "errored rows",
                str(report.baseline_errors),
                str(report.head_errors),
                report.errors_increased,
            )
        )
    known = None not in (report.baseline_abstained, report.head_abstained)
    if known and report.baseline_rows and report.head_rows:
        lines.append(
            (
                "abstained rows",
                f"{report.baseline_abstained}/{report.baseline_rows}",
                f"{report.head_abstained}/{report.head_rows}",
                report.abstained_increased,
            )
        )
    if report.questions_missing:
        total = report.baseline_rows or 0
        lines.append(
            (
                "questions covered",
                f"{total}/{total}",
                f"{total - (report.missing_questions or 0)}/{total}",
                True,
            )
        )
    return lines


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
        if item.missing:
            lines.append(f"| {item.metric} | {item.baseline:.4f} | missing | | **FAIL** |")
            continue
        flag = "**FAIL**" if item.dropped else "ok"
        lines.append(
            f"| {item.metric} | {item.baseline:.4f} | {item.head:.4f} "
            f"| {item.delta:+.4f} | {flag} |"
        )
    for name, value in report.new_metrics.items():
        lines.append(f"| {name} | n/a | {value:.4f} | | new, not gated |")
    for label, baseline, head, failed in row_check_lines(report):
        flag = "**FAIL**" if failed else "ok"
        lines.append(f"| {label} | {baseline} | {head} | | {flag} |")
    if explanation:
        lines += ["", explanation.strip()]
    return "\n".join(lines) + "\n"
