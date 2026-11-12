"""MkDocs hooks: the pages live in docs/site/, so give the site root a redirect to the home page."""

from pathlib import Path
from typing import Any

_REDIRECT = (
    '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>ReVal</title>'
    '<meta http-equiv="refresh" content="0; url=site/"><link rel="canonical" href="site/"></head>'
    '<body><a href="site/">ReVal documentation</a></body></html>\n'
)


def on_post_build(config: Any, **kwargs: Any) -> None:
    """Write site/index.html pointing at site/ (the Home page)."""
    Path(config["site_dir"], "index.html").write_text(_REDIRECT, encoding="utf-8")
