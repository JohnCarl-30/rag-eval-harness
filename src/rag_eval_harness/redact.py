from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit, urlunsplit


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    hostport = parts.netloc.split("@")[-1]
    if parts.username or parts.password:
        hostport = f"***@{hostport}"
    return urlunsplit((parts.scheme, hostport, parts.path, "", ""))


def redact_error(message: str | None, config: dict[str, Any] | None) -> str | None:
    if not message:
        return message
    data = config or {}
    token = data.get("token")
    if isinstance(token, str) and token:
        message = message.replace(token, "***")
    url = data.get("url")
    if isinstance(url, str) and url:
        message = message.replace(url, redact_url(url))
    return message


def redact_adapter_config(config: dict[str, Any] | None) -> dict[str, Any]:
    data = dict(config or {})
    if data.get("token"):
        data["token"] = "***"
    url = data.get("url")
    if isinstance(url, str) and url:
        data["url"] = redact_url(url)
    return data
