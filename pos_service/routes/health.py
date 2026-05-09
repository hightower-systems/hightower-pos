import asyncio
import time

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from pos_service import __version__
from pos_service.auth import get_current_user
from pos_service.clients import SentryClient
from pos_service.clients.sentry import SentryClientError, get_sentry_client
from pos_service.config import Settings, get_settings
from pos_service.models import POSUser

router = APIRouter(prefix="/api/health", tags=["health"])

SENTRY_PROBE_TIMEOUT_S = 2.0


class SentryHealth(BaseModel):
    reachable: bool
    latency_ms: int | None
    error: str | None


class WindcaveHealth(BaseModel):
    configured: bool
    mock: bool


class DependenciesResponse(BaseModel):
    version: str
    terminal_id: str
    sentry: SentryHealth
    windcave: WindcaveHealth


@router.get("/dependencies", response_model=DependenciesResponse)
async def dependencies(
    settings: Settings = Depends(get_settings),
    sentry: SentryClient = Depends(get_sentry_client),
    user: POSUser = Depends(get_current_user),
) -> DependenciesResponse:
    return DependenciesResponse(
        version=__version__,
        terminal_id=settings.windcave_station,
        sentry=await _probe_sentry(sentry),
        windcave=WindcaveHealth(
            configured=bool(
                settings.windcave_user
                and settings.windcave_key
                and settings.windcave_station
            ),
            mock=settings.windcave_mock,
        ),
    )


async def _probe_sentry(sentry: SentryClient) -> SentryHealth:
    if sentry.is_mock:
        return SentryHealth(reachable=True, latency_ms=0, error=None)
    started = time.perf_counter()
    try:
        await asyncio.wait_for(
            sentry.lookup_availability(sku="__health_probe__"),
            timeout=SENTRY_PROBE_TIMEOUT_S,
        )
    except SentryClientError as exc:
        if exc.status_code == 404:
            return SentryHealth(
                reachable=True,
                latency_ms=int((time.perf_counter() - started) * 1000),
                error=None,
            )
        return SentryHealth(reachable=False, latency_ms=None, error=str(exc))
    except (TimeoutError, Exception) as exc:
        return SentryHealth(reachable=False, latency_ms=None, error=str(exc))
    return SentryHealth(
        reachable=True,
        latency_ms=int((time.perf_counter() - started) * 1000),
        error=None,
    )
