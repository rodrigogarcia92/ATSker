"""FastAPI entry point.

`/health` deliberately touches no database and no model provider: Cloud Run uses
it to decide whether an instance is serving, and a check that depends on Neon's
scale-to-zero resume would fail exactly when it is needed most.
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from src import __version__
from src.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    is_production = settings.env == "production"

    app = FastAPI(
        title="ATSker",
        version=__version__,
        # The service is publicly reachable and authorization is in-app (PRD F1);
        # interactive docs would enumerate routes before any login exists.
        docs_url=None if is_production else "/docs",
        openapi_url=None if is_production else "/openapi.json",
        redoc_url=None,
    )

    @app.get("/health")
    def health() -> dict[str, object]:
        current = get_settings()
        return {
            "status": "ok",
            "version": __version__,
            "env": current.env,
            "configured": current.configured,
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        """Placeholder; M1 replaces this with the login page (PRD F1)."""
        return (
            "<!doctype html><html lang='es'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width, initial-scale=1'>"
            "<title>ATSker</title></head>"
            "<body style='font-family: system-ui; margin: 4rem auto; max-width: 34rem'>"
            f"<h1>ATSker</h1><p>v{__version__}</p>"
            "<p><a href='/health'>/health</a></p>"
            "</body></html>"
        )

    return app


app = create_app()
