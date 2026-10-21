import typer

app = typer.Typer(name="praxis", help="Praxis — turn commitments into completed work.", no_args_is_help=True)


@app.command()
def version() -> None:
    typer.echo("praxis 0.1.0 — scaffold")


@app.command()
def status() -> None:
    typer.echo("API status command is not wired yet. See docs/development/local-setup.md.")


if __name__ == "__main__":
    app()
