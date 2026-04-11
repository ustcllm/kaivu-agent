from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from .routes import (
    collaboration_router,
    events_router,
    experiments_router,
    graph_router,
    literature_router,
    memory_router,
    reports_router,
    threads_router,
    usage_router,
    workflow_router,
)
from .services.runtime import WorkflowRuntime


def create_app(root: str | Path | None = None) -> FastAPI:
    workspace_root = Path(root).resolve() if root is not None else Path(__file__).resolve().parent.parent
    web_root = workspace_root / "web"
    app = FastAPI(
        title="Kaivu Service",
        version="0.1.0",
        description="FastAPI wrapper around Kaivu's scientific multi-agent research workflow.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.state.workflow_runtime = WorkflowRuntime(workspace_root)
    app.include_router(workflow_router)
    app.include_router(collaboration_router)
    app.include_router(experiments_router)
    app.include_router(memory_router)
    app.include_router(graph_router)
    app.include_router(events_router)
    app.include_router(literature_router)
    app.include_router(reports_router)
    app.include_router(threads_router)
    app.include_router(usage_router)
    if web_root.exists():
        app.mount("/app", StaticFiles(directory=str(web_root), html=True), name="kaivu-web")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    async def root() -> RedirectResponse:
        target = "/app/" if web_root.exists() else "/docs"
        return RedirectResponse(url=target)

    return app


app = create_app()

