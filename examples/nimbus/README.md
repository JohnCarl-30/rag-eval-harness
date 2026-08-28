# Nimbus golden set

50 support questions for the Relaydesk demo tenant ([reasons.md](reasons.md)). The 2026-08-27 case study used the first 40.

`expected_slug` is ignored by the harness; it is there for humans.

Committed snapshots:

- `baseline.json` and `weak.json` (2026-08-27). 40-row article retriever vs top-1 no title boost. Leave these frozen.
- `chunked.json` and `hybrid-chunked.json` (2026-08-28). Paragraph index vs that 40-row article baseline.
- `evaluator-bench.json` (2026-08-28). Stub vs lexical wall clock on the 40-row baseline.
- `baseline-50.json` (2026-08-28). Lexical means on the current 50-row set, extractive `/api/eval`.
- `slice-15.jsonl` and `slice-15-lexical.json` (2026-08-28). Judge-vs-overlap slice. See [docs/nimbus-judge.md](../../docs/nimbus-judge.md).
