import asyncio
import getpass

import typer

from pos_service import __version__
from pos_service.auth import hash_password
from pos_service.clients.sentry import SentryClient
from pos_service.config import get_settings
from pos_service.db import get_session_factory
from pos_service.models import POSUser
from pos_service.services import reconciliation

app = typer.Typer(help="POS Service admin CLI", no_args_is_help=True)


@app.callback()
def _root() -> None:
    """POS Service admin CLI."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)


def _print_report(label: str, report: reconciliation.RetryReport) -> None:
    typer.echo(f"{label}: scanned {report.scanned}")
    typer.echo(f"  succeeded: {len(report.succeeded)}")
    for tid in report.succeeded:
        typer.echo(f"    {tid}")
    typer.echo(f"  still failing: {len(report.still_failing)}")
    for tid in report.still_failing:
        typer.echo(f"    {tid}")


@app.command("retry-failed-sales")
def retry_failed_sales_cmd() -> None:
    """Retry Sentry's POST /api/v1/pos/checkout for INVENTORY_UPDATE_FAILED rows."""
    settings = get_settings()
    sentry = SentryClient.from_settings(settings)
    factory = get_session_factory()

    async def _run() -> reconciliation.RetryReport:
        with factory() as db:
            return await reconciliation.retry_failed_sales(db, sentry)

    report = asyncio.run(_run())
    _print_report("retry-failed-sales", report)


@app.command("retry-failed-refunds")
def retry_failed_refunds_cmd() -> None:
    """Retry Sentry's POST /api/v1/pos/refund for REFUND_INVENTORY_UPDATE_FAILED rows."""
    settings = get_settings()
    sentry = SentryClient.from_settings(settings)
    factory = get_session_factory()

    async def _run() -> reconciliation.RetryReport:
        with factory() as db:
            return await reconciliation.retry_failed_refunds(db, sentry)

    report = asyncio.run(_run())
    _print_report("retry-failed-refunds", report)


@app.command("create-user")
def create_user(
    username: str = typer.Argument(..., help="Login username"),
    display_name: str = typer.Option(..., "--display-name", help="Display name"),
    require_password_change: bool = typer.Option(
        False,
        "--require-password-change/--no-require-password-change",
        help="Force the user to change their password on first login.",
    ),
) -> None:
    """Create a cashier login. Prompts for password."""
    pw1 = getpass.getpass("Password: ")
    pw2 = getpass.getpass("Confirm: ")
    if not pw1:
        typer.echo("Password cannot be empty.", err=True)
        raise typer.Exit(code=1)
    if pw1 != pw2:
        typer.echo("Passwords do not match.", err=True)
        raise typer.Exit(code=1)
    factory = get_session_factory()
    with factory() as db:
        if db.get(POSUser, username) is not None:
            typer.echo(f"User {username!r} already exists.", err=True)
            raise typer.Exit(code=1)
        db.add(
            POSUser(
                username=username,
                password_hash=hash_password(pw1),
                display_name=display_name,
                must_change_password=require_password_change,
            )
        )
        db.commit()
    typer.echo(f"Created user {username!r}.")
