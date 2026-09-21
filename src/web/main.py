"""FastAPI entry point.

`/health` deliberately touches no database and no model provider: Cloud Run uses
it to decide whether an instance is serving, and a check that depends on Neon's
scale-to-zero resume would fail exactly when it is needed most.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from src import __version__
from src.config import get_settings
from src.db import code_head_revision, database_revision
from src.web.deps import DbSession
from src.web.middleware import renew_session
from src.web.routes import analyze as analyze_routes
from src.web.routes import auth as auth_routes
from src.web.routes import bullets as bullet_routes
from src.web.routes import ingest as ingest_routes
from src.web.routes import letters as letter_routes
from src.web.routes import pages as page_routes
from src.web.routes import roles as role_routes
from src.web.routes import stories as story_routes
from src.web.routes import tracks as track_routes

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
    app.include_router(analyze_routes.router)
    app.include_router(role_routes.router)
    app.include_router(track_routes.router)
    app.include_router(bullet_routes.router)
    app.include_router(story_routes.router)
    app.include_router(letter_routes.router)
    app.include_router(ingest_routes.router)

    @app.get("/health")
    def health() -> dict[str, object]:
        current = get_settings()
        return {
            "status": "ok",
            "version": __version__,
            "env": current.env,
            "configured": current.configured,
        }

    @app.get("/health/schema")
    def health_schema(session: DbSession):
        """Whether the database is at the revision this code ships (2026-09-20).

        `/health` answers "is this instance serving" and must stay free of the
        database — a check that waits on Neon's scale-to-zero resume fails exactly
        when it is needed. This answers the other question an operator has: the
        image shipped at `0004` against a database at `0003` and every page behind
        the login returned 500 for a full deploy cycle, because `configured` only
        ever reported that the environment variable was *present*.

        Allowed to be slow, allowed to fail, and deliberately not wired to the Cloud
        Run probes: a service that serves a login page and a clear status is more
        useful than one that crash-loops. Unauthenticated like `/health`, and it
        exposes two revision strings — nothing an attacker could not guess from a
        public repository, and no connection string, host or credential.
        """
        database = database_revision(session)
        code = code_head_revision()
        match = bool(database) and database == code
        return JSONResponse(
            {"database": database, "code": code, "match": match},
            status_code=200 if match else 503,
        )

    return app


app = create_app()
