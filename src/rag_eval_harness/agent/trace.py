from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any

from pydantic_ai import AgentRunResult
from pydantic_ai.usage import RunUsage

USAGE_FIELDS = ("requests", "input_tokens", "output_tokens")


@dataclass
class TraceRecorder:
    """Collects one entry per agent run: messages, tool calls, tokens, and wall time."""

    runs: list[dict[str, Any]] = field(default_factory=list)

    @asynccontextmanager
    async def span(self, agent: str, **attrs: Any):
        entry: dict[str, Any] = {"agent": agent, **attrs}
        started = time.perf_counter()
        try:
            yield entry
        except Exception as exc:
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            entry["duration_ms"] = round((time.perf_counter() - started) * 1000, 1)
            self.runs.append(entry)

    @staticmethod
    def counts(usage: RunUsage | None) -> dict[str, int]:
        return {name: getattr(usage, name) if usage else 0 for name in USAGE_FIELDS}

    @staticmethod
    def finish(
        entry: dict[str, Any],
        result: AgentRunResult[Any],
        *,
        start: dict[str, int] | None = None,
    ) -> None:
        """Record usage since `start`. A delegated run shares its parent's usage object."""
        now = TraceRecorder.counts(result.usage)
        start = start or dict.fromkeys(USAGE_FIELDS, 0)
        entry["usage"] = {name: now[name] - start[name] for name in USAGE_FIELDS}
        entry["messages"] = json.loads(result.all_messages_json())

    def to_dict(self) -> dict[str, Any]:
        # A delegated run's usage is already inside its parent's, so totals skip it.
        top = [run for run in self.runs if not run.get("delegated")]
        return {
            "runs": self.runs,
            "totals": {
                name: sum(run.get("usage", {}).get(name, 0) for run in top) for name in USAGE_FIELDS
            },
        }


def enable_otel(service_name: str = "rag-eval") -> None:
    """Send Pydantic AI spans via Logfire: to Logfire with LOGFIRE_TOKEN, else OTEL_EXPORTER_*."""
    try:
        import logfire
    except ImportError as exc:
        raise RuntimeError(
            "--otel needs the trace extra. Run: pip install 'rag-eval-harness[trace]'"
        ) from exc
    logfire.configure(service_name=service_name, send_to_logfire="if-token-present", console=False)
    logfire.instrument_pydantic_ai()
