# Nimbus chunking case study

The first write-up asked what happens if we cut `k` and drop title boost. This one changes the index. Same golden set, same lexical scorer, same 0.05 gate. The support widget in **Relaydesk** (`~/Documents/relaydesk`) is still the system under test.

**Question:** if we split help articles into paragraphs, does context precision go up without a recall drop CI would reject?

**Answer:** precision more than doubled (**0.0634 → 0.1496**). Recall fell **0.8799 → 0.7816** (Δ **-0.0983**). `rag-eval regress --threshold 0.05` exits **1**. Production still retrieves whole articles.

## Setup

- Golden set: 40 questions ([`golden.csv`](../examples/nimbus/golden.csv)). 36 in-corpus, 4 out of scope.
- SUT: `POST /api/eval` with `{"question"}` → `{"answer","retrieved_contexts"}`. Extractive answers, no judge LLM.
- Scorer: `--evaluator lexical`.
- Article retriever (locked CI default): bag-of-words, top-3, title weight 4. Same snapshot as [`baseline.json`](../examples/nimbus/baseline.json).
- Chunked retriever: bodies split on blank lines, 32 paragraphs from 10 articles, title scored as a field, top-3 chunks (`?variant=chunked`).
- Hybrid-chunked: MiniLM + RRF over those paragraphs (`?variant=hybrid-chunked`). A/B only. CI does not download the model.

## Numbers (2026-08-28)

| Metric | Articles (baseline) | `chunked` | Delta | Gate (0.05) |
| --- | --- | --- | --- | --- |
| context_recall | 0.8799 | 0.7816 | -0.098 | FAIL |
| faithfulness | 0.7772 | 0.7543 | -0.023 | ok |
| answer_relevancy | 0.6381 | 0.5954 | -0.043 | ok |
| context_precision | 0.0634 | 0.1496 | +0.086 | ok |

Hit@1 / unique-slug hit@3 on 36 in-corpus rows: **30/36 → 29/36** and **35/36 → 31/36**.

Precision moved because `retrieved_contexts` are title + paragraph, not three full articles against a one-sentence reference. Recall failed because naive top-3 chunks are often three paragraphs from the same article. The labeled slug never gets a second chance.

Worst per-row recall drops vs articles: frontend read-key question, Starter retention, CSV row cap. Those answers live in a different article than the title-matched paragraphs.

`hybrid-chunked` keeps most of the precision gain (0.1564) and only loses 0.0291 recall, so it would pass the gate. Do not promote it. The widget still answers from whole articles, and the PR job cannot fetch `Xenova/all-MiniLM-L6-v2`.

Snapshots: [`baseline.json`](../examples/nimbus/baseline.json), [`chunked.json`](../examples/nimbus/chunked.json), [`hybrid-chunked.json`](../examples/nimbus/hybrid-chunked.json).

## Reproduce

Offline, no Relaydesk process:

```bash
cd ~/Documents/agentic-system
uv run rag-eval regress \
  --baseline examples/nimbus/baseline.json \
  --head examples/nimbus/chunked.json \
  --threshold 0.05
# expected: exit 1, context_recall FAIL

uv run rag-eval diff \
  --baseline examples/nimbus/baseline.json \
  --head examples/nimbus/chunked.json
```

Against a running app:

```bash
# terminal 1
cd ~/Documents/relaydesk && npm run dev

# terminal 2
cd ~/Documents/agentic-system
uv run rag-eval eval examples/nimbus/golden.csv \
  --sut-url 'http://127.0.0.1:3000/api/eval?variant=chunked' \
  --evaluator lexical --label nimbus-chunked -o /tmp/nimbus-chunked.json
uv run rag-eval regress \
  --baseline examples/nimbus/baseline.json \
  --head /tmp/nimbus-chunked.json \
  --threshold 0.05
```

What stayed in production: title-boosted top-3 **articles**. `chunked` and `hybrid-chunked` are A/B flags. The next knob is unique-slug after scoring chunks, not swapping the CI default.

Relaydesk notes: [`eval/README.md`](https://github.com/JohnCarl-30/relaydesk/blob/main/eval/README.md) in that repo.

## Record / post

```bash
./scripts/demo-chunking.sh
```

Means print, `context_recall FAIL`, exit 1. Same shape as [`./scripts/demo.sh`](../scripts/demo.sh) for the weak retriever.

Copy for LinkedIn (edit the first line if you want):

> I changed the index, not k, and the gate still said no.
> Same 40 Nimbus questions. Paragraph chunks doubled lexical context precision (0.063 → 0.150) and cut recall 0.880 → 0.782. CI failed at 0.05. Production still retrieves whole articles.
> Write-up: https://github.com/JohnCarl-30/rag-eval-harness/blob/main/docs/nimbus-chunking.md
> Resume: Chunked a help center to raise context precision (0.063 → 0.150); recall dropped 0.098 and failed a 0.05 CI gate, so production stayed on article-level retrieval.
