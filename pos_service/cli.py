import typer

from pos_service import __version__

app = typer.Typer(help="POS Service admin CLI", no_args_is_help=True)


@app.callback()
def _root() -> None:
    """POS Service admin CLI."""


@app.command()
def version() -> None:
    """Print the package version."""
    typer.echo(__version__)
