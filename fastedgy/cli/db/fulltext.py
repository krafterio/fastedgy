# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import json

from fastedgy import cli


@cli.command(name="fulltext-reindex")
@cli.option(
    "--model", default=None, help="API name of the model to reindex (e.g. 'task')"
)
@cli.option("--locale", default=None, help="Specific locale to reindex (e.g. 'fr')")
@cli.option(
    "--filter",
    "filter_json",
    default=None,
    help="JSON filter (X-Filter format), requires --model",
)
@cli.initialize_app
@cli.lifespan
async def fulltext_reindex(model, locale, filter_json, batch_size=500):
    """Reindex fulltext search vectors for all or specific models."""
    from edgy import monkay
    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service
    from fastedgy.orm.fields.field_fulltext import (
        get_searchable_fields,
        get_pg_language,
    )
    from sqlalchemy import text

    settings = get_service(BaseSettings)
    locales = [locale] if locale else settings.available_locales
    registry = monkay.instance.registry

    if filter_json and not model:
        cli.echo("Error: --filter requires --model", err=True)
        return

    # Find models with FulltextField
    fulltext_models = []
    for model_cls in registry.models.values():
        if model:
            api_name = str(model_cls.meta.tablename)
            model_name = model_cls.__name__.lower()
            if api_name != model and model_name != model:
                continue

        for field_name, field_info in model_cls.meta.fields.items():
            if getattr(field_info, "is_fulltext_field", False):
                searchable_fields = get_searchable_fields(model_cls)
                if searchable_fields:
                    fulltext_models.append((model_cls, field_name))

    if not fulltext_models:
        cli.echo("No models with FulltextField found.")
        return

    for model_cls, field_name in fulltext_models:
        tablename = str(model_cls.meta.tablename)
        searchable_fields = get_searchable_fields(model_cls)

        # Find primary key
        pk_field = None
        for fname, finfo in model_cls.meta.fields.items():
            if getattr(finfo, "primary_key", False):
                pk_field = fname
                break

        if not pk_field:
            cli.echo(f"  Skipping {model_cls.__name__}: no primary key found")
            continue

        for loc in locales:
            pg_language = get_pg_language(loc)
            column_name = f"{field_name}_{loc}"

            # Build tsvector expression from source fields
            tsvector_parts = []
            for src_field, weight in searchable_fields.items():
                tsvector_parts.append(
                    f"setweight(to_tsvector('{pg_language}', unaccent(coalesce({src_field}::text, ''))), '{weight}')"
                )

            if not tsvector_parts:
                continue

            tsvector_expr = " || ".join(tsvector_parts)

            # Build WHERE clause for optional filter
            where_clause = ""
            if filter_json:
                cli.echo(f"  Note: --filter is not supported in batch mode, ignoring")

            # Single batch SQL update — no ORM, no workspace filter
            sql = text(f"UPDATE {tablename} SET {column_name} = {tsvector_expr}")

            # Count total
            count_result = await model_cls.meta.registry.database.fetch_val(
                text(f"SELECT count(*) FROM {tablename}")
            )
            cli.echo(
                f"[{model_cls.__name__}/{loc}] Reindexing {count_result} records..."
            )

            await model_cls.meta.registry.database.execute(sql)

            cli.echo(f"  [{model_cls.__name__}/{loc}] Done.")

    cli.echo("Fulltext reindex complete.")


__all__ = [
    "fulltext_reindex",
]
