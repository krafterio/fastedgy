# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.cli import command, option, pass_cli_context, CliContext


@command()
@option('--host', default='0.0.0.0', help='Server host.')
@option('--port', default=8000, help='Server port.')
@option('--http-workers', default=None, help='Number of HTTP workers.')
@option('--reload/--no-reload', default=True, help='Enable/disable hot reload.')
@pass_cli_context
def serve(ctx: CliContext, host: str, port: int, http_workers: int | None, reload: bool):
    """Start the development server."""
    import uvicorn
    from fastedgy.cli import console, Table, Panel

    http_workers = ctx.settings.http_workers or http_workers
    http_workers = int(http_workers) if http_workers and not reload else None

    table = Table(title="Server Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")

    table.add_row("Host", host)
    table.add_row("Port", str(port))
    table.add_row("Mode", "development" if reload else "production")
    table.add_row("HTTP Workers", str(http_workers or 'auto'))
    table.add_row("Log Level", ctx.settings.log_level.value)
    table.add_row("Log Output", ctx.settings.log_output.value)
    table.add_row("URL", f"http://{host}:{port}")

    console.print(Panel(table, title=ctx.settings.title, border_style="blue"))

    uvicorn.run(
        ctx.settings.app_factory,
        factory=True,
        host=host,
        port=port,
        reload=reload,
        workers=http_workers,
        log_level=ctx.settings.log_level,
    )


__all__ = [
    "serve",
]
