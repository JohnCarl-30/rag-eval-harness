# Storage

SQLAlchemy 2.x. Tables are created automatically on startup.

## SQLite (default)

```bash
export DATABASE_URL=sqlite:///./rag_eval.db
rag-eval eval traces.jsonl
```

Fine for local use and the default Docker volume at `/data/rag_eval.db`.

## Postgres

```bash
pip install 'rag-eval-harness[postgres]'
export DATABASE_URL=postgresql+psycopg://rag:rag@localhost:5432/rag_eval
```

Compose optional profile:

```bash
docker compose --profile postgres up --build
# set DATABASE_URL=postgresql+psycopg://rag:rag@postgres:5432/rag_eval
```

## What is stored

- **datasets** — name, filename, row count
- **dataset_rows** — question, optional ground truth / answer / contexts
- **runs** — adapter config, evaluator, label, git SHA, status (`queued|running|completed|failed`), means, error count, `is_baseline`
- **run_scores** — per-row metrics and errors

Tagging a baseline clears `is_baseline` on other runs of the same dataset.

Jobs are in-process FastAPI background tasks. There is no Redis worker. Runs are capped at 100 rows.
