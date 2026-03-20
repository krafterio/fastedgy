# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import asyncio
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
@cli.option("--batch-size", default=500, help="Number of records per batch")
@cli.initialize_app
@cli.lifespan
async def fulltext_reindex(model, locale, filter_json, batch_size):
    """Reindex fulltext search vectors for all or specific models."""
    from edgy import monkay
    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service
    from fastedgy.orm.fields.field_fulltext import (
        get_searchable_fields,
        get_pg_language,
        escape_sql,
    )
    from fastedgy.orm.filter.builder import filter_query
    from sqlalchemy import text

    settings = get_service(BaseSettings)
    locales = [locale] if locale else settings.available_locales
    registry = monkay.instance.registry

    if filter_json and not model:
        cli.echo("Error: --filter requires --model", err=True)
        return

    # Parse filter if provided
    filter_value = None
    if filter_json:
        try:
            filter_value = json.loads(filter_json)
        except json.JSONDecodeError:
            cli.echo("Error: --filter must be valid JSON", err=True)
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

            # Build query
            query = model_cls.query

            if filter_value:
                query = filter_query(query, filter_value)

            # Count total
            total = await query.count()
            cli.echo(f"[{model_cls.__name__}/{loc}] {total} records to reindex...")

            processed = 0
            offset = 0

            while offset < total:
                records = await query.offset(offset).limit(batch_size).all()

                for record in records:
                    record_pk = getattr(record, pk_field)

                    # Build tsvector expression with bind parameters
                    tsvector_parts = []
                    bind_params = {"pk_value": record_pk}

                    for idx, (src_field, weight) in enumerate(
                        searchable_fields.items()
                    ):
                        value = getattr(record, src_field, None)
                        if isinstance(value, dict):
                            value = value.get(loc)
                        if value is None:
                            value = ""
                        else:
                            value = str(value)

                        param_name = f"val_{idx}"
                        bind_params[param_name] = value
                        tsvector_parts.append(
                            f"setweight(to_tsvector('{pg_language}', unaccent(coalesce(:{param_name}, ''))), '{weight}')"
                        )

                    if tsvector_parts:
                        tsvector_expr = " || ".join(tsvector_parts)
                        sql = text(
                            f"UPDATE {tablename} SET {column_name} = {tsvector_expr} "
                            f"WHERE {pk_field} = :pk_value"
                        )
                        await model_cls.meta.registry.database.execute(sql, bind_params)

                    processed += 1

                offset += batch_size
                cli.echo(
                    f"  [{model_cls.__name__}/{loc}] {min(processed, total)}/{total} records..."
                )

            cli.echo(f"  [{model_cls.__name__}/{loc}] Done.")

    cli.echo("Fulltext reindex complete.")


__all__ = [
    "fulltext_reindex",
]
