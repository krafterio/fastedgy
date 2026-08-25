# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).


from fastedgy import cli


@cli.command(name="fulltext-reindex")
@cli.option("--model", default=None, help="API name of the model to reindex (e.g. 'task')")
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
    from sqlalchemy import text

    from fastedgy.config import BaseSettings
    from fastedgy.dependencies import get_service
    from fastedgy.orm import Registry
    from fastedgy.orm.fields.field_fulltext import (
        build_tsvector_expression,
        get_fulltext_column,
        get_primary_key_field,
        get_searchable_fields,
    )

    settings = get_service(BaseSettings)
    locales = [locale] if locale else settings.available_locales
    registry = get_service(Registry)

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
        pk_field = get_primary_key_field(model_cls)

        if not pk_field:
            cli.echo(f"  Skipping {model_cls.__name__}: no primary key found")
            continue

        for loc in locales:
            tsvector_expr = build_tsvector_expression(model_cls, loc)
            column_name = get_fulltext_column(model_cls, field_name, loc)

            if tsvector_expr is None or column_name is None:
                continue

            if filter_json:
                cli.echo("  Note: --filter is not supported in batch mode, ignoring")

            # Single batch SQL update — no ORM, no workspace filter. The
            # IS DISTINCT FROM keeps the pass idempotent: a rerun rewrites only
            # the rows whose vector is actually wrong, instead of every row and
            # its GIN entries.
            target = f'"{column_name}"'
            sql = text(
                f"UPDATE {tablename} SET {target} = {tsvector_expr} WHERE {target} IS DISTINCT FROM ({tsvector_expr})"
            )

            count_result = await model_cls.meta.registry.database.fetch_val(text(f"SELECT count(*) FROM {tablename}"))
            cli.echo(f"[{model_cls.__name__}/{loc}] Reindexing {count_result} records...")

            updated = await model_cls.meta.registry.database.execute(sql)

            cli.echo(f"  [{model_cls.__name__}/{loc}] Done ({updated} rewritten).")

    cli.echo("Fulltext reindex complete.")


__all__ = [
    "fulltext_reindex",
]
