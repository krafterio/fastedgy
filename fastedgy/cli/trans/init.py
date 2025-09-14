# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.cli import argument, option, pass_cli_context, CliContext, console
from fastedgy.cli.trans import trans
from fastedgy.config import BaseSettings
from fastedgy.i18n import I18nExtractor


@trans.command()
@argument("locale", type=str)
@option(
    "--package", type=str, help="Target a specific package instead of the main project"
)
@pass_cli_context
def init(ctx: CliContext, locale: str, package: str | None = None):
    """Initialize a new locale by creating a .po file with all translatable strings."""
    settings = ctx.get(BaseSettings)
    extractor = I18nExtractor(settings)

    if package:
        console.print(
            f"[blue]Initializing translations for locale '{locale}' in package '{package}'...[/blue]"
        )
    else:
        console.print(
            f"[blue]Initializing translations for locale '{locale}'...[/blue]"
        )

    result = extractor.init(locale, package)

    if result.success:
        console.print(f"Found {result.strings_found} translatable strings")
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]Error: {result.error}[/red]")
        if "already exists" in result.error:
            console.print(
                f"[yellow]Use 'kt trans extract {locale}' to update existing translations[/yellow]"
            )
