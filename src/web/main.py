"""FastAPI entry point.

`/health` deliberately touches no database and no model provider: Cloud Run uses
it to decide whether an instance is serving, and a check that depends on Neon's
scale-to-zero resume would fail exactly when it is needed most.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from src import __version__
from src.config import get_settings
from src.web.middleware import renew_session
from src.web.routes import auth as auth_routes
from src.web.routes import pages as page_routes

STATIC_DIR = Path(__file__).parent / "static"


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

    app.middleware("http")(renew_session)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    app.include_router(auth_routes.router)
    app.include_router(page_routes.router)

    @app.get("/health")
    def health() -> dict[str, object]:
        current = get_settings()
        return {
            "status": "ok",
            "version": __version__,
            "env": current.env,
            "configured": current.configured,
        }

    return app


app = create_app()
