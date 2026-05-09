from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pos_service import __version__
from pos_service.config import Settings, get_settings
from pos_service.db import get_engine
from pos_service.routes import admin as admin_routes
from pos_service.routes import auth as auth_routes
from pos_service.routes import checkout as checkout_routes
from pos_service.routes import items as items_routes
from pos_service.routes import prices as prices_routes
from pos_service.routes import refunds as refunds_routes


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="hightower-pos", version=__version__)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health(engine: Engine = Depends(get_engine)) -> dict[str, str]:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "version": __version__}

    app.include_router(auth_routes.router)
    app.include_router(items_routes.router)
    app.include_router(prices_routes.router)
    app.include_router(checkout_routes.router)
    app.include_router(refunds_routes.router)
    app.include_router(admin_routes.router)

    return app


app = create_app()
