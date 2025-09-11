# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import rich_click as click


def main():
    cli()


@click.group(invoke_without_command=True)
def cli():
    """
    FastEdgy CLI
    """
    pass
