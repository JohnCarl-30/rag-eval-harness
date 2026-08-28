#!/usr/bin/env python3
"""Canned FAQ RAG stand-in. POST /query with {\"question\"}."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KNOWLEDGE: list[tuple[list[str], str, str]] = [
    (
        ["office hours", "hours", "open"],
        "The Acme Docs team is available 09:00–17:00 Pacific Time, Monday through Friday.",
        "Internal handbook §1: Office hours are 9am–5pm PT on weekdays.",
    ),
    (
        ["vpn", "wireguard"],
        "Use WireGuard. Download the profile from the IT portal under Network → VPN.",
        "IT portal: Network → VPN → WireGuard profile. Do not share the config.",
    ),
    (
        ["pto", "vacation", "time off"],
        "Full-time staff receive 20 days of PTO each calendar year, accrued monthly.",
        "People ops policy: 20 PTO days per year, accrued monthly, request in Workday.",
    ),
    (
        ["expense", "receipt", "reimburse"],
        "Expenses under $75 do not need a receipt. Submit larger expenses within 30 days.",
        "Finance FAQ: receipts required at $75 and above; 30-day submission window.",
    ),
    (
        ["oncall", "on-call", "pager"],
        "Primary on-call rotates weekly. Page via PagerDuty service 'docs-search'.",
        "On-call runbook: weekly rotation, PagerDuty service docs-search.",
    ),
    (
        ["reset password", "password"],
        "Reset your password at https://id.acme.example/reset. MFA is required.",
        "Identity docs: password reset URL and MFA requirement.",
    ),
    (
        ["staging", "stage environment"],
        "The staging cluster is staging.acme.example. It refreshes from prod nightly at 02:00 UTC.",
        "Platform notes: staging.acme.example nightly refresh 02:00 UTC.",
    ),
    (
        ["sla", "uptime"],
        "Search API SLA is 99.9% monthly availability, excluding planned maintenance windows.",
        "SRE handbook: 99.9% monthly SLA for the search API.",
    ),
    (
        ["chunk", "chunk size"],
        "Default chunk size is 512 tokens with 64 tokens of overlap.",
        "RAG config: chunk_size=512, overlap=64.",
    ),
    (
        ["embedding", "embed model"],
        "Production embeddings use text-embedding-3-small with 1536 dimensions.",
        "Model card: text-embedding-3-small, 1536-d vectors.",
    ),
    (
        ["rate limit", "throttle"],
        "The public API allows 60 requests per minute per API key.",
        "API gateway: 60 req/min per key.",
    ),
    (
        ["retention", "logs"],
        "Application logs are retained for 30 days. Audit logs are retained for 1 year.",
        "Compliance: app logs 30 days, audit logs 365 days.",
    ),
    (
        ["support", "ticket"],
        "Open a ticket in #docs-help or email support@acme.example.",
        "Support channels: Slack #docs-help and support@acme.example.",
    ),
    (
        ["index", "reindex"],
        "The corpus reindexes every 6 hours. Manual reindex is available to admins.",
        "Indexer: scheduled every 6 hours; admins can trigger a full rebuild.",
    ),
    (
        ["language", "languages"],
        "The assistant answers in English. Uploaded docs may be English or Spanish.",
        "i18n notes: answers in English; corpus languages: en, es.",
    ),
    (
        ["cómo contacto", "contacto a soporte", "soporte"],
        "Abre un ticket en #docs-help o escribe a support@acme.example.",
        "Soporte: Slack #docs-help y support@acme.example.",
    ),
]

FALLBACK_ANSWER = "I do not have that in the Acme Docs corpus."
FALLBACK_CONTEXT = "No matching handbook section was retrieved."


def retrieve(question: str) -> tuple[str, list[str]]:
    q = question.lower()
    for keywords, answer, context in KNOWLEDGE:
        if any(token in q for token in keywords):
            return answer, [context]
    return FALLBACK_ANSWER, [FALLBACK_CONTEXT]


class Handler(BaseHTTPRequestHandler):
    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/", "/health"}:
            self._json(200, {"status": "ok", "service": "dummy-rag"})
            return
        self._json(404, {"detail": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path not in {"/query", "/"}:
            self._json(404, {"detail": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            self._json(400, {"detail": "invalid json"})
            return
        question = ""
        if isinstance(payload, dict):
            question = str(payload.get("question") or payload.get("user_input") or "")
        if not question.strip():
            self._json(400, {"detail": "question is required"})
            return
        answer, contexts = retrieve(question)
        self._json(200, {"answer": answer, "retrieved_contexts": contexts})

    def log_message(self, fmt: str, *args: object) -> None:
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Canned FAQ RAG for rag-eval-harness demos")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"dummy-rag listening on http://{args.host}:{args.port}/query", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
