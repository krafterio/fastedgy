# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.cli import command, option, pass_cli_context, CliContext


@command()
@option("--host", default="0.0.0.0", help="Server host.")
@option("--port", default=8000, help="Server port.")
@option("--http-workers", default=None, help="Number of HTTP workers.")
@option(
    "--http-limit-concurrency", default=None, help="Number of HTTP limit concurrency."
)
@option("--reload/--no-reload", default=True, help="Enable/disable hot reload.")
@pass_cli_context
def serve(
    ctx: CliContext,
    host: str,
    port: int,
    http_workers: int | None,
    http_limit_concurrency: int | None,
    reload: bool,
):
    """Start the development server."""
    import os
    import uvicorn
    from fastedgy.cli import console, Table, Panel

    http_workers = ctx.settings.http_workers or http_workers
    http_workers = int(http_workers) if http_workers and not reload else None
    http_limit_concurrency = (
        ctx.settings.http_limit_concurrency or http_limit_concurrency
    )
    http_limit_concurrency = (
        int(http_limit_concurrency) if http_limit_concurrency and not reload else None
    )

    table = Table(title="Server Configuration")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", style="green")

    if http_workers is None:
        auto_workers = int(os.environ.get("WEB_CONCURRENCY", 1))
        http_workers_display = f"auto ({auto_workers})"
    else:
        http_workers_display = str(http_workers)

    if http_limit_concurrency is None:
        http_limit_concurrency_display = f"auto"
    else:
        http_limit_concurrency_display = str(http_limit_concurrency)

    db_pool_size = ctx.settings.computed_database_pool_size
    db_max_overflow = ctx.settings.computed_database_max_overflow
    db_pool_display = (
        str(ctx.settings.database_pool_size)
        if ctx.settings.database_pool_size is not None
        else f"auto ({db_pool_size})"
    )
    db_overflow_display = (
        str(ctx.settings.database_max_overflow)
        if ctx.settings.database_max_overflow is not None
        else f"auto ({db_max_overflow})"
    )

    table.add_row("Host", host)
    table.add_row("Port", str(port))
    table.add_row("Mode", "development" if reload else "production")
    table.add_row("HTTP Workers", http_workers_display)
    table.add_row("HTTP Limit Concurrency", http_limit_concurrency_display)
    table.add_row("DB Pool Size", db_pool_display)
    table.add_row("DB Max Overflow", db_overflow_display)
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
        limit_concurrency=http_limit_concurrency,
        log_level=ctx.settings.log_level,
    )


__all__ = [
    "serve",
]
