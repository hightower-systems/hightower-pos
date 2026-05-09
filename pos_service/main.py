import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.engine import Engine

from pos_service import __version__
from pos_service.clients.fabric import FabricClient
from pos_service.config import Settings, get_settings
from pos_service.db import get_engine, get_session_factory
from pos_service.routes import admin as admin_routes
from pos_service.routes import auth as auth_routes
from pos_service.routes import checkout as checkout_routes
from pos_service.routes import health as health_routes
from pos_service.routes import items as items_routes
from pos_service.routes import prices as prices_routes
from pos_service.routes import refunds as refunds_routes
from pos_service.services.fabric_outbox import run_loop as fabric_outbox_loop
from pos_service.services.fabric_price_sync import run_loop as fabric_sync_loop

log = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        fabric_client = FabricClient.from_settings(settings)
        background_tasks: list[asyncio.Task[None]] = []

        if fabric_client.is_mock:
            log.info("fabric_workers_disabled_mock_mode")
        else:
            session_factory = get_session_factory()
            background_tasks.append(
                asyncio.create_task(
                    fabric_sync_loop(
                        fabric_client,
                        session_factory,
                        settings.fabric_sync_interval_s,
                    ),
                    name="fabric_price_sync",
                )
            )
            background_tasks.append(
                asyncio.create_task(
                    fabric_outbox_loop(
                        fabric_client,
                        session_factory,
                        settings.fabric_outbox_drain_interval_s,
                        batch_size=settings.fabric_outbox_batch_size,
                    ),
                    name="fabric_outbox_drain",
                )
            )

        try:
            yield
        finally:
            for task in background_tasks:
                task.cancel()
            for task in background_tasks:
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            await fabric_client.aclose()

    app = FastAPI(title="hightower-pos", version=__version__, lifespan=lifespan)

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
    app.include_router(health_routes.router)

    return app


app = create_app()
