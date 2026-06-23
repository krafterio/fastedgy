# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.cli import command, option, pass_cli_context, CliContext


def _build_uvicorn_log_config(settings) -> dict | None:
    """Return a uvicorn ``log_config`` dict that routes uvicorn's own loggers
    through :class:`fastedgy.logger.JsonFormatter` when JSON format is selected.

    Returning ``None`` keeps uvicorn's default text-based config, so non-JSON
    formats stay backward-compatible.
    """
    import os
    from fastedgy.logger import LogFormat, LogOutput

    if settings.log_format != LogFormat.JSON:
        return None

    handlers: dict = {}
    handler_names: list[str] = []

    if settings.log_output in (LogOutput.CONSOLE, LogOutput.BOTH):
        handlers["stdout"] = {
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",
            "formatter": "json",
        }
        handler_names.append("stdout")

    if settings.log_output in (LogOutput.FILE, LogOutput.BOTH):
        log_dir = os.path.dirname(settings.log_path)
        os.makedirs(log_dir, exist_ok=True)
        handlers["file"] = {
            "class": "logging.FileHandler",
            "filename": settings.log_path,
            "formatter": "json",
        }
        handler_names.append("file")

    level = settings.log_level.value.upper()

    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": "fastedgy.logger.JsonFormatter"},
        },
        "handlers": handlers,
        "loggers": {
            "uvicorn": {
                "handlers": handler_names,
                "level": level,
                "propagate": False,
            },
            "uvicorn.error": {
                "handlers": handler_names,
                "level": level,
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": handler_names,
                "level": level,
                "propagate": False,
            },
        },
    }


@command()
@option("--host", default="0.0.0.0", help="Server host.")
@option("--port", default=8000, help="Server port.")
@option("--http-workers", default=None, help="Number of HTTP workers.")
@option("--http-limit-concurrency", default=None, help="Number of HTTP limit concurrency.")
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
    from fastedgy.cli import console, Table, Panel, cli_json_log
    from fastedgy.logger import LogFormat

    http_workers = ctx.settings.http_workers or http_workers
    http_workers = int(http_workers) if http_workers and not reload else None
    http_limit_concurrency = ctx.settings.http_limit_concurrency or http_limit_concurrency
    http_limit_concurrency = int(http_limit_concurrency) if http_limit_concurrency and not reload else None

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

    config = {
        "host": host,
        "port": port,
        "mode": "development" if reload else "production",
        "http_workers": http_workers_display,
        "http_limit_concurrency": http_limit_concurrency_display,
        "db_pool_size": db_pool_display,
        "db_max_overflow": db_overflow_display,
        "log_level": ctx.settings.log_level.value,
        "log_output": ctx.settings.log_output.value,
        "log_format": ctx.settings.log_format.value
        if hasattr(ctx.settings.log_format, "value")
        else str(ctx.settings.log_format),
        "url": f"http://{host}:{port}",
    }

    if ctx.settings.log_format == LogFormat.JSON:
        cli_json_log("fastedgy.cli.serve", ctx.settings.title, config=config)
    else:
        table = Table(title="Server Configuration")
        table.add_column("Parameter", style="cyan")
        table.add_column("Value", style="green")
        table.add_row("Host", host)
        table.add_row("Port", str(port))
        table.add_row("Mode", config["mode"])
        table.add_row("HTTP Workers", http_workers_display)
        table.add_row("HTTP Limit Concurrency", http_limit_concurrency_display)
        table.add_row("DB Pool Size", db_pool_display)
        table.add_row("DB Max Overflow", db_overflow_display)
        table.add_row("Log Level", ctx.settings.log_level.value)
        table.add_row("Log Output", ctx.settings.log_output.value)
        table.add_row("URL", config["url"])
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
        log_config=_build_uvicorn_log_config(ctx.settings),
    )


__all__ = [
    "serve",
]
