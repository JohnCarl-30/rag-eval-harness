from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from rag_eval_harness import __version__
from rag_eval_harness.api.auth import ApiKeyMiddleware, bind_requires_auth
from rag_eval_harness.api.routes import router
from rag_eval_harness.config import get_settings
from rag_eval_harness.store.repo import Store


def find_web_dist() -> Path | None:
    here = Path(__file__).resolve()
    candidates = [here.parents[1] / "web_dist", Path.cwd() / "web" / "dist"]
    if len(here.parents) > 3:
        candidates.append(here.parents[3] / "web" / "dist")
    for path in candidates:
        if (path / "index.html").is_file():
            return path
    return None


def create_app(
    store: Store | None = None,
    *,
    bind_host: str | None = None,
    api_key: str | None = None,
) -> FastAPI:
    settings = get_settings()
    host = bind_host if bind_host is not None else os.environ.get("RAG_EVAL_HOST", settings.host)
    env_key = os.environ.get("RAG_EVAL_API_KEY") or settings.api_key
    key = api_key if api_key is not None else env_key
    auth_required = bind_requires_auth(host)

    app = FastAPI(
        title="rag-eval-harness",
        version=__version__,
        description="Evaluate RAG pipelines, persist runs, and diff against a tagged baseline.",
    )
    app.state.store = store or Store(settings.database_url)
    app.state.auth_required = auth_required
    app.state.api_key = key

    app.add_middleware(ApiKeyMiddleware, enabled=auth_required, api_key=key)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(router)

    dist = find_web_dist()
    if dist is not None:
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/"):
                from fastapi import HTTPException

                raise HTTPException(status_code=404, detail="Not found")
            candidate = dist / full_path
            if full_path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist / "index.html")

    return app
