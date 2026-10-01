# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy import cli


@cli.group()
def storage():
    """Storage management commands."""


@storage.command(name="set-class")
@cli.argument("storage_class")
@cli.option("--dry-run", is_flag=True, default=False, help="Count what would move without copying anything")
@cli.option("--workers", default=16, help="Objects copied at once")
@cli.initialize_app
async def set_class(storage_class: str, dry_run: bool, workers: int):
    """Move every stored object to an S3 storage class (EXPRESS_ONEZONE is OVHcloud High Performance)."""
    from fastedgy.dependencies import get_service
    from fastedgy.storage import Storage
    from fastedgy.storage.adapters.s3 import S3Adapter

    adapter = get_service(Storage).adapter

    if not isinstance(adapter, S3Adapter):
        raise cli.ClickException("The storage adapter is not s3: its files have no storage class")

    moved, size, skipped = await adapter.set_storage_class(storage_class, dry_run=dry_run, workers=workers)

    verb = "would move" if dry_run else "moved"
    cli.console.print(f"[green]{moved} object(s) {verb} to {storage_class}, {size / 1024**3:.2f} GiB[/green]")

    if skipped:
        cli.console.print(f"[yellow]{skipped} object(s) over 5 GiB left in their class[/yellow]")
