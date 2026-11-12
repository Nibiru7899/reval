"""FastAPI layer over the application services (docs/09). Needs the ``server`` extra."""

from reval.api.app import create_app
from reval.api.settings import ApiSettings

__all__ = ["ApiSettings", "create_app"]
