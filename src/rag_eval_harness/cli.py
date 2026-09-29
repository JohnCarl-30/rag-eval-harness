from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Annotated

import typer
from dotenv import load_dotenv

from rag_eval_harness import __version__
from rag_eval_harness.config import get_settings
from rag_eval_harness.engine import eval_from_path
from rag_eval_harness.regression.compare import (
    DEFAULT_THRESHOLD,
    RegressionReport,
    compare_means,
    load_errors_ref,
    load_means_ref,
    load_rows_ref,
    worst_row_drops,
)
from rag_eval_harness.store.repo import Store

load_dotenv()

app = typer.Typer(
    no_args_is_help=True,
    add_completion=False,
    help="Evaluate RAG pipelines, persist runs, and gate regressions.",
)

DbOption = Annotated[
    str | None,
    typer.Option("--db", envvar="DATABASE_URL", help="SQLAlchemy URL (SQLite or Postgres)."),
]


def _store(db: str | None) -> Store:
    return Store(db or get_settings().database_url)


def _print_run(run, summary=None) -> None:
    typer.echo(f"Run id:     {run.id}")
    typer.echo(f"Dataset:    {run.dataset_id}")
    typer.echo(f"Status:     {run.status}")
    typer.echo(f"Evaluator:  {run.evaluator}")
    typer.echo(f"Adapter:    {run.adapter_type}")
    if run.label:
        typer.echo(f"Label:      {run.label}")
    if run.git_sha:
        typer.echo(f"Git SHA:    {run.git_sha}")
    means = (summary.means if summary else None) or run.means or {}
    error_count = summary.error_count if summary else run.error_count
    typer.echo(f"Errors:     {error_count}")
    if means:
        typer.echo("Means:")
        for name, value in means.items():
            typer.echo(f"  {name}: {value:.4f}")
    if run.status == "failed" and run.error_message:
        typer.echo(f"Error:      {run.error_message}")


def _print_errors(report) -> None:
    if report.baseline_errors is None or report.head_errors is None:
        return
    flag = "FAIL" if report.errors_increased else "ok"
    typer.echo(
        f"  {'errored rows':20} baseline={report.baseline_errors}  "
        f"head={report.head_errors}  {flag}"
    )


def _print_report(report: RegressionReport) -> None:
    typer.echo(f"threshold: {report.threshold}")
    typer.echo(f"baseline:  {report.baseline_ref}")
    typer.echo(f"head:      {report.head_ref}")
    for item in report.deltas:
        flag = "FAIL" if item.dropped else "ok"
        typer.echo(
            f"  {item.metric:20} baseline={item.baseline:.4f}  head={item.head:.4f}  "
            f"delta={item.delta:+.4f}  {flag}"
        )
    _print_errors(report)


def _version_callback(value: bool) -> None:
    if value:
        typer.echo(__version__)
        raise typer.Exit()


@app.callback()
def _root(
    version: Annotated[
        bool,
        typer.Option("--version", callback=_version_callback, is_eager=True),
    ] = False,
) -> None:
    return


@app.command()
def serve(
    host: Annotated[str, typer.Option(help="Bind address.")] = "",
    port: Annotated[int, typer.Option(help="Bind port.")] = 0,
) -> None:
    """Start the FastAPI app (serves the React UI when web/dist is present)."""
    settings = get_settings()
    bind_host = host or settings.host
    bind_port = port or settings.port
    os.environ["RAG_EVAL_HOST"] = bind_host
    os.environ["RAG_EVAL_PORT"] = str(bind_port)
    import uvicorn

    from rag_eval_harness.api.app import create_app
    from rag_eval_harness.api.auth import bind_requires_auth

    needs_key = bind_requires_auth(bind_host)
    has_key = os.environ.get("RAG_EVAL_API_KEY") or settings.api_key
    if needs_key and not has_key:
        typer.echo(
            "RAG_EVAL_API_KEY is required when binding a non-loopback address.",
            err=True,
        )
        raise typer.Exit(1)

    stale = _store(None).fail_interrupted_runs()
    if stale:
        typer.echo(f"Marked {stale} interrupted run(s) as failed.", err=True)
    uvicorn.run(create_app(), host=bind_host, port=bind_port)


@app.command()
def eval(  # noqa: A001 — matches the public CLI contract
    source: Annotated[Path, typer.Argument(help="CSV/JSONL/JSON golden set or traces.")],
    sut_url: Annotated[
        str | None,
        typer.Option("--sut-url", help="HTTP SUT POST {question} → {answer, retrieved_contexts}."),
    ] = None,
    sut_token: Annotated[
        str | None,
        typer.Option("--sut-token", help="Optional bearer token sent to the SUT."),
    ] = None,
    evaluator: Annotated[str, typer.Option(help="stub, lexical, or ragas.")] = "stub",
    timeout: Annotated[float, typer.Option(help="Per-row HTTP timeout in seconds.")] = 30.0,
    label: Annotated[str | None, typer.Option(help="Optional run label.")] = None,
    git_sha: Annotated[str | None, typer.Option(help="Optional git SHA to record.")] = None,
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write a JSON snapshot (means + run id)."),
    ] = None,
    db: DbOption = None,
) -> None:
    """Score traces or call an HTTP RAG, then persist the run."""
    store = _store(db)
    try:
        run, summary = eval_from_path(
            store,
            source,
            sut_url=sut_url,
            sut_token=sut_token,
            timeout=timeout,
            evaluator=evaluator,
            label=label,
            git_sha=git_sha,
        )
    except Exception as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    _print_run(run, summary)
    if output:
        payload = store.snapshot(run.id)
        payload["rows"] = [row.to_dict() for row in summary.rows]
        output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        typer.echo(f"Wrote {output}")


@app.command()
def baseline(
    run_id: Annotated[str, typer.Argument(help="Run to tag as the dataset baseline.")],
    db: DbOption = None,
) -> None:
    """Mark a completed run as the baseline for its dataset."""
    store = _store(db)
    run = store.get_run(run_id)
    if run is None:
        typer.echo(f"Run not found: {run_id}", err=True)
        raise typer.Exit(2)
    if run.status != "completed":
        typer.echo(f"Only a completed run can be a baseline (status={run.status})", err=True)
        raise typer.Exit(2)
    run = store.set_baseline(run_id)
    typer.echo(f"Tagged {run.id} as baseline for dataset {run.dataset_id}")


@app.command()
def regress(
    baseline_ref: Annotated[
        str,
        typer.Option("--baseline", help="Baseline run id or JSON snapshot path."),
    ],
    head_ref: Annotated[
        str,
        typer.Option("--head", help="Head run id or JSON snapshot path."),
    ],
    threshold: Annotated[
        float,
        typer.Option("--threshold", help="Fail if any mean drops by more than this."),
    ] = DEFAULT_THRESHOLD,
    db: DbOption = None,
) -> None:
    """Compare mean metrics. Exit 1 if any mean drops by more than --threshold
    or head has more errored rows than baseline."""
    store = _store(db)
    try:
        b_ref, b_means = load_means_ref(baseline_ref, store)
        h_ref, h_means = load_means_ref(head_ref, store)
        b_errors = load_errors_ref(baseline_ref, store)
        h_errors = load_errors_ref(head_ref, store)
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    report = compare_means(
        b_means,
        h_means,
        threshold=threshold,
        baseline_ref=b_ref,
        head_ref=h_ref,
        baseline_errors=b_errors,
        head_errors=h_errors,
    )
    _print_report(report)
    if not report.passed:
        typer.echo("Regression detected.", err=True)
        raise typer.Exit(1)
    typer.echo("No regression.")


@app.command()
def diff(
    baseline_ref: Annotated[
        str,
        typer.Option("--baseline", help="Baseline run id or JSON snapshot path."),
    ],
    head_ref: Annotated[
        str,
        typer.Option("--head", help="Head run id or JSON snapshot path."),
    ],
    metric: Annotated[
        str | None,
        typer.Option("--metric", help="Only rank drops for this metric name."),
    ] = None,
    limit: Annotated[int, typer.Option("--limit", help="How many per-row drops to print.")] = 8,
    threshold: Annotated[
        float,
        typer.Option("--threshold", help="Shown on the mean table. This command does not fail CI."),
    ] = DEFAULT_THRESHOLD,
    db: DbOption = None,
) -> None:
    """Print mean deltas and the worst per-row drops. Use regress to fail CI."""
    store = _store(db)
    try:
        b_ref, b_means = load_means_ref(baseline_ref, store)
        h_ref, h_means = load_means_ref(head_ref, store)
        b_errors = load_errors_ref(baseline_ref, store)
        h_errors = load_errors_ref(head_ref, store)
        _, b_rows = load_rows_ref(baseline_ref, store)
        _, h_rows = load_rows_ref(head_ref, store)
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    report = compare_means(
        b_means,
        h_means,
        threshold=threshold,
        baseline_ref=b_ref,
        head_ref=h_ref,
        baseline_errors=b_errors,
        head_errors=h_errors,
    )
    _print_report(report)
    drops = worst_row_drops(b_rows, h_rows, metric=metric, limit=limit)
    if not drops:
        typer.echo("No per-row drops.")
        return
    typer.echo("Worst per-row drops:")
    for item in drops:
        question = item.question.replace("\n", " ").strip()
        if len(question) > 80:
            question = question[:77] + "..."
        typer.echo(
            f"  [{item.index}] {item.metric}  {item.baseline:.4f} -> {item.head:.4f}  "
            f"({-item.drop:+.4f})  {question}"
        )


@app.command()
def investigate(
    baseline_ref: Annotated[
        str,
        typer.Option("--baseline", help="Baseline run id or JSON snapshot path."),
    ],
    head_ref: Annotated[
        str,
        typer.Option("--head", help="Head run id or JSON snapshot path."),
    ],
    threshold: Annotated[
        float,
        typer.Option("--threshold", help="Fail if any mean drops by more than this."),
    ] = DEFAULT_THRESHOLD,
    limit: Annotated[
        int,
        typer.Option("--limit", help="Worst rows per failing stage sent to the model."),
    ] = 5,
    model: Annotated[
        str | None,
        typer.Option(
            "--model",
            envvar="RAG_EVAL_AGENT_MODEL",
            help="Pydantic AI model string. Default: openai-chat:$OPENAI_MODEL.",
        ),
    ] = None,
    mode: Annotated[
        str,
        typer.Option(
            "--mode",
            help="workflow: fixed triage/diagnose/summarize graph. "
            "supervisor: one agent picks its own tools.",
        ),
    ] = "workflow",
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Write the investigation as JSON."),
    ] = None,
    trace: Annotated[
        Path | None,
        typer.Option("--trace", help="Write every agent run (messages, tools, tokens) as JSON."),
    ] = None,
    otel: Annotated[
        bool,
        typer.Option("--otel", help="Send spans via Logfire / OTLP. Needs the trace extra."),
    ] = False,
    db: DbOption = None,
) -> None:
    """Run the regress gate, then have agents explain a failure. Exit code matches regress."""
    if mode not in ("workflow", "supervisor"):
        typer.echo(f"Unknown --mode {mode!r}. Use 'workflow' or 'supervisor'.", err=True)
        raise typer.Exit(2)
    try:
        from rag_eval_harness.agent.graph import investigate as run_investigation
        from rag_eval_harness.agent.trace import TraceRecorder, enable_otel
    except ImportError as exc:
        typer.echo(
            "The agent extra is not installed. Run: pip install 'rag-eval-harness[agent]'",
            err=True,
        )
        raise typer.Exit(2) from exc
    if otel:
        try:
            enable_otel()
        except RuntimeError as exc:
            typer.echo(str(exc), err=True)
            raise typer.Exit(2) from exc
    store = _store(db)
    try:
        b_ref, b_means = load_means_ref(baseline_ref, store)
        h_ref, h_means = load_means_ref(head_ref, store)
        _, b_rows = load_rows_ref(baseline_ref, store)
        _, h_rows = load_rows_ref(head_ref, store)
        b_errors = load_errors_ref(baseline_ref, store)
        h_errors = load_errors_ref(head_ref, store)
    except (KeyError, ValueError, OSError, json.JSONDecodeError) as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from exc
    report = compare_means(
        b_means,
        h_means,
        threshold=threshold,
        baseline_ref=b_ref,
        head_ref=h_ref,
        baseline_errors=b_errors,
        head_errors=h_errors,
    )
    _print_report(report)
    if report.passed:
        typer.echo("No regression. Nothing to investigate.")
        return
    model_name = model or f"openai-chat:{get_settings().openai_model}"
    typer.echo(f"Investigating ({mode}) with {model_name}...")
    recorder = TraceRecorder()
    try:
        result = asyncio.run(
            run_investigation(
                report,
                b_rows,
                h_rows,
                model=model_name,
                limit=limit,
                mode=mode,
                recorder=recorder,
            )
        )
    except Exception as exc:
        # The gate already failed. A broken model call must not turn that into a pass.
        typer.echo(f"Investigation failed: {exc}", err=True)
        typer.echo("Regression detected.", err=True)
        raise typer.Exit(1) from exc
    finally:
        if trace:
            trace.write_text(json.dumps(recorder.to_dict(), indent=2), encoding="utf-8")
            typer.echo(f"Wrote trace {trace}")
    typer.echo("")
    typer.echo(result.to_markdown())
    if output:
        output.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")
        typer.echo(f"Wrote {output}")
    typer.echo("Regression detected.", err=True)
    raise typer.Exit(1)


@app.command("runs")
def list_runs(
    dataset_id: Annotated[str | None, typer.Option("--dataset")] = None,
    db: DbOption = None,
) -> None:
    """List persisted runs."""
    store = _store(db)
    runs = store.list_runs(dataset_id)
    if not runs:
        typer.echo("No runs.")
        return
    for run in runs:
        marker = "*" if run.is_baseline else " "
        typer.echo(
            f"{marker} {run.id}  {run.status:10}  {run.evaluator:6}  {run.adapter_type:6}  "
            f"errors={run.error_count}  {run.label or ''}"
        )
