# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.cli import argument, option, pass_cli_context, CliContext, console
from fastedgy.cli.trans import trans
from fastedgy.config import BaseSettings
from fastedgy.i18n import I18nExtractor


@trans.command()
@argument("locale", type=str, required=False)
@option(
    "--package", type=str, help="Target a specific package instead of the main project"
)
@pass_cli_context
def extract(ctx: CliContext, locale: str | None = None, package: str | None = None):
    """Extract translatable strings and update .po files."""
    settings = ctx.get(BaseSettings)
    extractor = I18nExtractor(settings)

    pkg_info = f" for package '{package}'" if package else ""
    if locale:
        console.print(
            f"[blue]Extracting translations for locale: {locale}{pkg_info}[/blue]"
        )
    else:
        console.print(f"[blue]Extracting translations for all locales{pkg_info}[/blue]")

    result = extractor.extract(locale, package)

    if result.success:
        console.print(f"Found {result.strings_found} translatable strings")
        console.print(f"[green]{result.message}[/green]")
    else:
        console.print(f"[red]Error: {result.error}[/red]")
