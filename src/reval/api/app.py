"""``create_app``: FastAPI application factory. The OpenAPI schema is the contract for the TS client."""

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from reval import __version__
from reval.api.deps import AppState
from reval.api.routes import claims, diff, evidence, graph, health, jobs, plans, projects, reports, snapshots
from reval.api.settings import ApiSettings
from reval.errors import RevalError

API_PREFIX = "/api/v1"


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
    return app
