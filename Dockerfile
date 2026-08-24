# syntax=docker/dockerfile:1

FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS api
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    RAG_EVAL_HOST=0.0.0.0 \
    RAG_EVAL_PORT=8000 \
    DATABASE_URL=sqlite:////data/rag_eval.db
COPY --from=ghcr.io/astral-sh/uv:0.11.6 /uv /usr/local/bin/uv
COPY pyproject.toml README.md LICENSE uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev --extra postgres --no-editable
COPY --from=web /web/dist /app/web/dist
COPY examples ./examples
RUN mkdir -p /data
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["rag-eval", "serve", "--host", "0.0.0.0", "--port", "8000"]
