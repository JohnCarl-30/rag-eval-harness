from __future__ import annotations

from rag_eval_harness.redact import redact_adapter_config, redact_error, redact_url


def test_redact_url_strips_userinfo_query_and_fragment() -> None:
    raw = "https://user:s3cret@rag.example:8443/eval?api_key=SUPERSECRET#frag"
    assert redact_url(raw) == "https://***@rag.example:8443/eval"


def test_redact_adapter_config() -> None:
    out = redact_adapter_config(
        {
            "url": "https://rag.example/eval?api_key=SUPERSECRET",
            "token": "tok_live_xyz",
            "timeout": 30,
        }
    )
    assert out["token"] == "***"
    assert out["url"] == "https://rag.example/eval"
    assert out["timeout"] == 30
    assert "SUPERSECRET" not in str(out)
    assert "tok_live_xyz" not in str(out)


def test_redact_error_replaces_token_and_url() -> None:
    config = {
        "url": "https://rag.example/eval?api_key=SUPERSECRET",
        "token": "tok_live_xyz",
    }
    message = "http adapter: GET https://rag.example/eval?api_key=SUPERSECRET tok_live_xyz"
    out = redact_error(message, config)
    assert out is not None
    assert "SUPERSECRET" not in out
    assert "tok_live_xyz" not in out
    assert "***" in out
