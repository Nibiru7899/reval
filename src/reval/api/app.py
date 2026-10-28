"""``create_app``: FastAPI application factory. The OpenAPI schema is the contract for the TS client."""

import os
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.responses import Response
from starlette.types import Scope

from reval import __version__
from reval.api.deps import AppState
from reval.api.routes import claims, diff, evidence, graph, health, jobs, plans, projects, reports, snapshots
from reval.api.settings import ApiSettings
from reval.errors import RevalError

API_PREFIX = "/api/v1"

# The built web UI (``npm --prefix web run build``); REVAL_WEB_DIST overrides it.
DEFAULT_WEB_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"


class _SpaFiles(StaticFiles):
    """Static files whose unknown paths fall back to ``index.html``, so client-side routes deep-link."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404 or path.replace("\\", "/").startswith("api/"):
                raise
            return await super().get_response("index.html", scope)


def web_dist() -> Path | None:
    """The built SPA directory if one exists (it is optional: the API works without it)."""
    env = os.environ.get("REVAL_WEB_DIST")
    dist = Path(env) if env else DEFAULT_WEB_DIST
    return dist if (dist / "index.html").is_file() else None


def _operation_id(route: APIRoute) -> str:
    """Function names double as operation ids, so the generated client has clean method names."""
    return route.name


def create_app(settings: ApiSettings | None = None) -> FastAPI:
    """Build the app. The project is opened lazily on the first request that needs it."""
    app = FastAPI(
        title="ReVal API",
        version=__version__,
        openapi_url=f"{API_PREFIX}/openapi.json",
        docs_url=f"{API_PREFIX}/docs",
        redoc_url=None,
        generate_unique_id_function=_operation_id,
    )
    app.state.reval = AppState(settings or ApiSettings.from_env())

    @app.exception_handler(RevalError)
    async def _reval_error(_: Request, exc: RevalError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": " ".join(str(exc).split())})

    api = APIRouter(prefix=API_PREFIX)
    for module in (health, projects, snapshots, diff, claims, evidence, graph, plans, jobs, reports):
        api.include_router(module.router)
    app.include_router(api)
    dist = web_dist()
    if dist is not None:  # mounted last, so every API route wins over the catch-all
        app.mount("/", _SpaFiles(directory=dist, html=True), name="web")
    return app
