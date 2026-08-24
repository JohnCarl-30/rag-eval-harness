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

You should receive an acknowledgement within 7 days. After this repository is on GitHub, prefer GitHub private vulnerability reporting.

## Notes for operators

- Bind loopback (`127.0.0.1`) for local use; set `RAG_EVAL_API_KEY` whenever the API listens on a non-loopback address
- Treat SUT bearer tokens and OpenAI keys as secrets; the API redacts adapter tokens in responses
- The stub evaluator does not call a model and does not need `OPENAI_API_KEY`
