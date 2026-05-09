import logging
from datetime import UTC, datetime

import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from print_agent import __version__
from print_agent.config import Settings, get_settings
from print_agent.escpos_client import StarTSP100

log = logging.getLogger(__name__)


_printer: StarTSP100 | None = None
_last_print_at: datetime | None = None


def get_printer() -> StarTSP100:
    if _printer is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={"error": "printer_not_initialised"},
        )
    return _printer


def set_printer(printer: StarTSP100 | None) -> None:
    global _printer
    _printer = printer


class PrintRequest(BaseModel):
    format: str = Field(default="text", pattern="^(text)$")
    content: str
    cut: bool = True
    open_drawer_after: bool = False


class PrintResponse(BaseModel):
    success: bool
    printer_status: str


class StatusResponse(BaseModel):
    agent_status: str
    agent_version: str
    printer_online: bool
    last_print_at: datetime | None


class DrawerResponse(BaseModel):
    success: bool


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    allowed = settings.allowed_origin

    app = FastAPI(title="hightower-pos-print-agent", version=__version__)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[allowed],
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def origin_check(request: Request, call_next):
        if request.method == "OPTIONS":
            return await call_next(request)
        origin = request.headers.get("origin")
        if origin != allowed:
            return JSONResponse(
                status_code=status.HTTP_403_FORBIDDEN,
                content={"error": "forbidden_origin"},
            )
        return await call_next(request)

    @app.post("/print", response_model=PrintResponse)
    def print_endpoint(
        body: PrintRequest, printer: StarTSP100 = Depends(get_printer)
    ) -> PrintResponse:
        try:
            printer.print_text(body.content, cut=body.cut)
            if body.open_drawer_after:
                printer.open_drawer(pin=settings.drawer_pin)
        except Exception as exc:
            log.exception("print failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "printer_offline", "message": str(exc)},
            ) from exc
        global _last_print_at
        _last_print_at = datetime.now(UTC).replace(tzinfo=None)
        return PrintResponse(success=True, printer_status="ok")

    @app.post("/open-drawer", response_model=DrawerResponse)
    def open_drawer_endpoint(
        printer: StarTSP100 = Depends(get_printer),
    ) -> DrawerResponse:
        try:
            printer.open_drawer(pin=settings.drawer_pin)
        except Exception as exc:
            log.exception("open-drawer failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "drawer_offline", "message": str(exc)},
            ) from exc
        return DrawerResponse(success=True)

    @app.get("/status", response_model=StatusResponse)
    def status_endpoint(
        printer: StarTSP100 = Depends(get_printer),
    ) -> StatusResponse:
        return StatusResponse(
            agent_status="online",
            agent_version=__version__,
            printer_online=printer.is_online(),
            last_print_at=_last_print_at,
        )

    @app.post("/test-print", response_model=PrintResponse)
    def test_print_endpoint(
        printer: StarTSP100 = Depends(get_printer),
    ) -> PrintResponse:
        body = (
            "AvidMax Print Agent\n"
            f"Version: {__version__}\n"
            f"{datetime.now(UTC).replace(tzinfo=None):%Y-%m-%d %H:%M:%S}\n"
            "If you can read this, the\nprinter is wired correctly.\n"
        )
        try:
            printer.print_text(body, cut=True)
        except Exception as exc:
            log.exception("test-print failed")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "printer_offline", "message": str(exc)},
            ) from exc
        global _last_print_at
        _last_print_at = datetime.now(UTC).replace(tzinfo=None)
        return PrintResponse(success=True, printer_status="ok")

    return app


def _bootstrap_printer(settings: Settings) -> None:
    star = StarTSP100.open_usb(
        vendor_id=settings.printer_vendor_id,
        product_id=settings.printer_product_id,
        profile=settings.printer_profile,
    )
    set_printer(star)
    if settings.print_test_on_startup:
        try:
            star.print_text(
                f"AvidMax Print Agent v{__version__} online.\n", cut=True
            )
        except Exception:
            log.warning("startup test print failed")


def main() -> None:
    settings = get_settings()
    logging.basicConfig(level=settings.log_level)
    _bootstrap_printer(settings)
    uvicorn.run(
        create_app(settings),
        host=settings.listen_host,
        port=settings.listen_port,
        log_level=settings.log_level.lower(),
    )


app = create_app()


if __name__ == "__main__":
    main()
