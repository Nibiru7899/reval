from fastapi import APIRouter

from reval import __version__
from reval.api.schemas import Health

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> Health:
    """Liveness probe; does not open the project."""
    return Health(status="ok", version=__version__)
