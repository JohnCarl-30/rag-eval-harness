# Security policy

## Supported versions

| Version | Supported |
| --- | --- |
| 0.1.x | yes |

## Reporting a vulnerability

Do not file a public issue for security problems.

Email **johncarlsantos30@gmail.com** with:

- a description of the issue
- steps to reproduce
- impact (for example: unauthenticated access when `RAG_EVAL_API_KEY` is required)

You should receive an acknowledgement within 7 days. Prefer GitHub private vulnerability reporting on this repository's Security tab.

## Notes for operators

- Bind loopback (`127.0.0.1`) for local use. Set `RAG_EVAL_API_KEY` whenever the API listens on a non-loopback address.
- A dataset is capped at 100 rows. Ten thousand rows would need a worker queue this project will not add.
- Treat SUT bearer tokens and OpenAI keys as secrets. The API redacts adapter tokens and strips userinfo, query, and fragment from SUT URLs in responses.
- HTTP row errors are short codes (timeout, HTTP status, exception class). They do not include the request URL.
- Each HTTP row has its own timeout (default 30s). A hung SUT becomes a row error, not a hung process.
- The stub evaluator does not call a model and does not need `OPENAI_API_KEY`.
- `rag-eval investigate` sends up to `--limit` rows per failing stage to the configured model provider: question, ground truth, answers, and clipped contexts. `regress` and `diff` send nothing.
- `investigate --otel` spans include prompts and responses, so that row text also goes to the tracing backend. `--trace` files hold the same text on disk.
