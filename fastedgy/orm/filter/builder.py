# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import Any, cast

from sqlalchemy import (
    Text as SaText,
    Uuid as SaUuid,
    and_ as sa_and,
    cast as sa_cast,
    exists,
    not_ as sa_not,
    or_ as sa_or,
    select as sa_select,
    literal_column,
    text,
)

from fastedgy.orm import Model
from fastedgy.orm.fields import (
    BaseFieldType,
    IntegerField,
    UUIDField,
    DateField,
    DateTimeField,
    DecimalField,
    FloatField,
    ManyToMany,
    generic_target_name,
    resolve_generic_pair,
)
from fastedgy.orm.query import QuerySet
from fastedgy.orm.manager import BaseManager
from fastedgy.orm.utils import find_primary_key_field
from fastedgy.orm.filter.types import (
    InvalidFilterError,
    FilterRule,
    FilterCondition,
    Filter,
    FilterTuple,
)
from fastedgy.orm.filter.operators import (
    FILTER_OPERATORS_SQL,
    FILTER_DICT_OPERATORS_SQL,
    FILTER_OPERATORS_SQL_UNPACK,
)
from fastedgy.orm.filter.parser import parse_filter_input
from fastedgy.orm.filter.validator import validate_filters
from fastedgy.orm.filter.utils import _has_duplicating_relation_filter, _convert_value
from fastedgy.orm.filter.search_parser import parse_search_input
from fastedgy.orm.fields.field_fulltext import get_pg_language


def _get_cond_query(model_cls: type[Model]) -> QuerySet:
    """Helper to get the query object for building conditions."""
    return cast(
        QuerySet,
        model_cls.global_query if hasattr(model_cls, "global_query") else model_cls.query,
    )


_PATTERN_OPERATORS = {
    "like",
    "ilike",
    "not like",
    "not ilike",
    "starts with",
    "ends with",
    "not starts with",
    "not ends with",
    "contains",
    "icontains",
    "not contains",
    "not icontains",
}


def build_filter_expression(model_cls: type[Model], filters: FilterRule | FilterCondition | None) -> Any | None:
    if filters is None:
        return None

    if isinstance(filters, FilterRule):
        field = filters.field
        operator_method = FILTER_OPERATORS_SQL.get(filters.operator, None)
        operator_dict_method = FILTER_DICT_OPERATORS_SQL.get(filters.operator, None)

        # Special case: fulltext search operators
        if filters.operator == "search":
            return _build_fulltext_search_expression(model_cls, field, filters.value)

        if filters.operator == "search_fuzzy":
            return _build_fulltext_fuzzy_expression(model_cls, field, filters.value)

        if not operator_method or not operator_dict_method:
            raise InvalidFilterError(f"Operator '{filters.operator}' is not supported")

        # Paths crossing a generic reverse relation cannot be delegated to the
        # ORM lookup joins: route them through the EXISTS builder, which knows
        # how to join on the (model, id) column pair.
        if "." in field and _path_crosses_generic_relation(model_cls, field):
            expression = _build_exists_expression(model_cls, filters)
            if expression is None:
                raise InvalidFilterError(f"Cannot filter through the generic relation path '{field}'")
            return expression

        use_col = field.startswith("extra_") or resolve_generic_pair(model_cls, field) is not None
        field_type = _find_field_type_in_model(model_cls, field)

        if "." not in field and getattr(field_type, "is_generic_foreign_key", False):
            return _build_generic_reference_expression(model_cls, cast(Any, field_type), filters)

        # Pattern operators build a LIKE: a UUID column must be compared as
        # text (PostgreSQL has no uuid ~~ text operator).
        if "." not in field and filters.operator in _PATTERN_OPERATORS and isinstance(field_type, UUIDField):
            column = _find_column_in_model(model_cls, field)
            return operator_method(sa_cast(column, SaText()), str(filters.value))

        related_columns = getattr(field_type, "related_columns", None)
        if related_columns:
            field += "." + list(related_columns.keys())[0]

        column = _find_column_in_model(model_cls, field)
        value = _convert_value_by_field_type(model_cls, field, filters.value)

        if filters.operator in FILTER_OPERATORS_SQL_UNPACK:
            unpack_count = FILTER_OPERATORS_SQL_UNPACK[filters.operator]

            if not isinstance(value, (list, tuple)) or len(value) < unpack_count:
                raise InvalidFilterError(f"Operator '{filters.operator}' requires {unpack_count} values in list")

            if use_col:
                return column.between(*value)
            return operator_dict_method(_get_cond_query(model_cls), field, value)

        if use_col:
            return operator_method(column, value)
        return operator_dict_method(_get_cond_query(model_cls), field, value)

    if not filters.rules:
        return None

    is_or = filters.condition == "|"

    expressions = []

    for rule in filters.rules:
        # For OR conditions, use EXISTS subqueries for relation-based rules
        # to ensure each branch evaluates independently with its own JOIN context
        if is_or and isinstance(rule, FilterRule) and "." in rule.field:
            expr = _build_exists_expression(model_cls, rule)
        else:
            expr = None

        if expr is None:
            expr = build_filter_expression(model_cls, rule)

        if expr is not None:
            expressions.append(expr)

    if not expressions:
        return None

    if len(expressions) == 1:
        return expressions[0]

    cond_query = _get_cond_query(model_cls)

    if is_or:
        return cond_query.or_(*expressions)

    return cond_query.and_(*expressions)


def _build_exists_expression(model_cls: type[Model], filters: FilterRule) -> Any | None:
    """
    Build an EXISTS subquery for a relation-based filter rule.

    Used for relation-based rules in OR conditions to ensure each branch
    evaluates independently with its own JOIN context, instead of sharing
    JOINs with other branches.
    """
    field = filters.field
    operator_method = FILTER_OPERATORS_SQL.get(filters.operator, None)

    if not operator_method:
        return None

    value = _convert_value_by_field_type(model_cls, field, filters.value)

    # Resolve field type and append related column if the leaf is a relation
    field_type = _find_field_type_in_model(model_cls, field)
    resolved_field = field

    related_columns = getattr(field_type, "related_columns", None)
    if related_columns:
        resolved_field += "." + list(related_columns.keys())[0]

    parts = resolved_field.split(".")
    current_model = model_cls
    from_table = None
    root_link_condition = None
    join_entries = []  # list of (table, join_condition) for subsequent JOINs

    for i, part in enumerate(parts[:-1]):
        field_info = current_model.meta.fields[part]

        if isinstance(field_info, ManyToMany):
            # Many-to-many: hop through the intermediate table, then to the target.
            # A M2M field also exposes `target`, so it must be handled before the
            # forward-FK branch or it would be mistaken for one (and lacks
            # `related_columns`, which that branch relies on).
            through_model = getattr(field_info, "through", None)
            target_model = getattr(field_info, "target", None)
            from_fk = getattr(field_info, "from_foreign_key", None)  # through -> current model
            to_fk = getattr(field_info, "to_foreign_key", None)  # through -> target model

            if (
                through_model is None
                or target_model is None
                or not from_fk
                or not to_fk
                or not hasattr(through_model, "table")
                or not hasattr(target_model, "table")
            ):
                return None

            current_pk = find_primary_key_field(current_model)
            target_pk = find_primary_key_field(target_model)

            if current_pk is None or target_pk is None:
                return None

            through_table = through_model.table
            target_table = target_model.table

            if from_table is None:
                from_table = through_table
                root_link_condition = through_table.columns[from_fk] == model_cls.table.columns[current_pk]
            else:
                join_entries.append(
                    (
                        through_table,
                        through_table.columns[from_fk] == current_model.table.columns[current_pk],
                    )
                )

            join_entries.append(
                (
                    target_table,
                    target_table.columns[target_pk] == through_table.columns[to_fk],
                )
            )

            current_model = target_model

        elif hasattr(field_info, "related_from"):
            # Reverse relation (OneToMany): related_model has FK pointing back
            related_model = getattr(field_info, "related_from")

            # Find the FK field on related_model whose related_name == part
            fk_field_name = None
            fk_field = None
            for fname, finfo in related_model.meta.fields.items():
                if getattr(finfo, "related_name", None) == part:
                    fk_field_name = fname
                    fk_field = finfo
                    break

            if fk_field_name is None:
                return None

            current_pk = find_primary_key_field(current_model)

            if current_pk is None:
                return None

            if getattr(fk_field, "is_generic_foreign_key", False):
                # Generic reverse relation: join on the id column AND pin the
                # model column to the current model's generic target name.
                generic_field = cast(Any, fk_field)
                target_name = generic_target_name(current_model)
                source_table = model_cls.table if from_table is None else current_model.table
                link_condition = sa_and(
                    related_model.table.columns[generic_field.id_column] == source_table.columns[current_pk],
                    related_model.table.columns[generic_field.model_column] == target_name,
                )

                if from_table is None:
                    from_table = related_model.table
                    root_link_condition = link_condition
                else:
                    join_entries.append((related_model.table, link_condition))
            elif from_table is None:
                from_table = related_model.table
                root_link_condition = related_model.table.columns[fk_field_name] == model_cls.table.columns[current_pk]
            else:
                join_entries.append(
                    (
                        related_model.table,
                        related_model.table.columns[fk_field_name] == current_model.table.columns[current_pk],
                    )
                )

            current_model = related_model

        elif hasattr(field_info, "target"):
            # Forward FK
            related_model = getattr(field_info, "target")
            pk_col = list(getattr(field_info, "related_columns").keys())[0]

            if from_table is None:
                from_table = related_model.table
                root_link_condition = related_model.table.columns[pk_col] == model_cls.table.columns[part]
            else:
                join_entries.append(
                    (
                        related_model.table,
                        related_model.table.columns[pk_col] == current_model.table.columns[part],
                    )
                )

            current_model = related_model

        elif hasattr(field_info, "related_model"):
            related_model = getattr(field_info, "related_model")

            if from_table is None:
                from_table = related_model.table
                root_link_condition = related_model.table.columns["id"] == model_cls.table.columns[part]
            else:
                join_entries.append(
                    (
                        related_model.table,
                        related_model.table.columns["id"] == current_model.table.columns[part],
                    )
                )

            current_model = related_model
        else:
            return None

    if from_table is None or root_link_condition is None:
        return None

    # Final column and filter condition
    final_column = current_model.table.columns[parts[-1]]

    if filters.operator in _PATTERN_OPERATORS and isinstance(getattr(final_column, "type", None), SaUuid):
        # A UUID column compares as text under pattern operators (PostgreSQL
        # has no uuid ~~ text operator).
        filter_cond = operator_method(sa_cast(final_column, SaText()), str(filters.value))
    elif filters.operator in FILTER_OPERATORS_SQL_UNPACK:
        filter_cond = final_column.between(*value)
    elif filters.operator in ("is true", "is false", "is empty", "is not empty"):
        filter_cond = operator_method(final_column)
    else:
        filter_cond = operator_method(final_column, value)

    # Build EXISTS subquery with independent JOINs
    select_from = from_table
    for table, cond in join_entries:
        select_from = select_from.join(table, cond)

    subq = sa_select(literal_column("1")).select_from(select_from).where(root_link_condition).where(filter_cond)

    return exists(subq)


def filter_query(
    query: QuerySet | BaseManager,
    filters: str | list | FilterTuple | Filter | None,
    restrict_error: bool = False,
    allow_excluded: bool = False,
) -> QuerySet:
    has_filters = filters is not None
    query = cast(QuerySet, query)

    try:
        if not isinstance(filters, FilterCondition) and not isinstance(filters, FilterRule):
            filters = parse_filter_input(filters)

        if not has_filters and not filters:
            return query

        if has_filters and not filters:
            raise InvalidFilterError("Invalid format of filters")

        filters = validate_filters(query.model_class, filters, allow_excluded=allow_excluded)
    except InvalidFilterError:
        if has_filters and restrict_error:
            primary_key = find_primary_key_field(query.model_class)

            if primary_key:
                return query.filter({f"{primary_key}__is": None})

        raise

    expression = build_filter_expression(query.model_class, filters)

    if expression is not None:
        query = query.filter(expression)

        if _has_duplicating_relation_filter(query.model_class, filters) and query.distinct_on is None:
            primary_key = find_primary_key_field(query.model_class)
            if primary_key:
                query = query.distinct(primary_key)

    # Add ts_rank extra_select for fulltext search fields
    query = _add_fulltext_rank_extra_select(query, filters)

    return query


def _get_fulltext_locale() -> str:
    """Get the current locale from the fastedgy execution context."""
    try:
        from fastedgy import context

        return context.get_locale()
    except Exception:
        return "en"


def _resolve_fulltext_field(model_cls: type[Model], field_path: str) -> tuple[type[Model], str, str]:
    """
    Resolve a fulltext field path (e.g. "search_value" or "task_category.search_value")
    to the target model class, tablename, and leaf field name.

    Returns:
        (target_model_cls, tablename, leaf_field_name)
    """
    parts = field_path.split(".")
    current_cls = model_cls

    for part in parts[:-1]:
        field_info = current_cls.meta.fields.get(part)
        if field_info is None:
            break
        if hasattr(field_info, "target"):
            current_cls = field_info.target
        elif hasattr(field_info, "related_from"):
            current_cls = field_info.related_from
        else:
            break

    return current_cls, str(current_cls.meta.tablename), parts[-1]


def _build_fulltext_search_expression(model_cls: type[Model], field_path: str, value: Any) -> Any:
    """
    Build a fulltext search WHERE expression:
    tablename.column_locale @@ to_tsquery('language', unaccent('parsed_tsquery'))
    """
    target_cls, tablename, field_name = _resolve_fulltext_field(model_cls, field_path)
    locale = _get_fulltext_locale()
    pg_language = get_pg_language(locale)
    column_name = f"{field_name}_{locale}"

    parsed = parse_search_input(value)
    if not parsed:
        return None

    try:
        return text(f"{tablename}.{column_name} @@ to_tsquery('{pg_language}', unaccent(:search_value))").bindparams(
            search_value=parsed
        )
    except Exception:
        return text(f"{tablename}.{column_name} @@ to_tsquery('{pg_language}', :search_value)").bindparams(
            search_value=parsed
        )


def _fuzzy_correct_sql(column_name: str, tablename: str, term: str, param_name: str) -> str:
    """
    Build a SQL subquery that corrects a single term via ts_stat + pg_trgm similarity.
    Returns the corrected word or the original term if no match.
    All done in a single SQL expression — no round-trip.
    """
    return (
        f"coalesce("
        f"(SELECT word FROM ts_stat('SELECT {column_name} FROM {tablename}') "
        f"WHERE similarity(word, :{param_name}) > 0.3 "
        f"ORDER BY similarity(word, :{param_name}) DESC LIMIT 1), "
        f":{param_name})"
    )


def _build_fulltext_fuzzy_expression(model_cls: type[Model], field_path: str, value: Any) -> Any:
    """
    Build a fulltext search expression with inline fuzzy term correction.
    Each term is corrected via a ts_stat subquery using pg_trgm similarity,
    then used in a standard tsquery. All in one SQL query, sync, no round-trip.
    """
    from fastedgy.orm.filter.search_parser import _tokenize

    target_cls, tablename, field_name = _resolve_fulltext_field(model_cls, field_path)
    locale = _get_fulltext_locale()
    pg_language = get_pg_language(locale)
    column_name = f"{field_name}_{locale}"

    raw_value = value.strip()
    if not raw_value:
        return None

    tokens = _tokenize(raw_value)
    if not tokens:
        return None

    tsquery_parts = []
    bind_params = {}
    param_idx = 0

    for token in tokens:
        if token.type == "phrase":
            # Correct each word in the phrase
            phrase_words = token.value.split(" <-> ")
            corrected_words = []
            for word in phrase_words:
                param_name = f"ft_{param_idx}"
                bind_params[param_name] = word
                corrected_words.append(_fuzzy_correct_sql(column_name, tablename, word, param_name))
                param_idx += 1
            # phrase: word1 <-> word2 (no :*)
            phrase_expr = " || ' <-> ' || ".join(corrected_words)
            tsquery_parts.append(("mandatory", f"({phrase_expr})"))

        elif token.type == "mandatory":
            bare = token.value.rstrip(":*")
            param_name = f"ft_{param_idx}"
            bind_params[param_name] = bare
            corrected = _fuzzy_correct_sql(column_name, tablename, bare, param_name)
            tsquery_parts.append(("mandatory", f"({corrected} || ':*')"))
            param_idx += 1

        elif token.type == "excluded":
            bare = token.value.rstrip(":*")
            param_name = f"ft_{param_idx}"
            bind_params[param_name] = bare
            corrected = _fuzzy_correct_sql(column_name, tablename, bare, param_name)
            tsquery_parts.append(("excluded", f"({corrected} || ':*')"))
            param_idx += 1

        else:  # bare
            bare = token.value.rstrip(":*")
            param_name = f"ft_{param_idx}"
            bind_params[param_name] = bare
            corrected = _fuzzy_correct_sql(column_name, tablename, bare, param_name)
            tsquery_parts.append(("optional", f"({corrected} || ':*')"))
            param_idx += 1

    if not tsquery_parts:
        return None

    # Build the combined tsquery expression
    optional = [expr for typ, expr in tsquery_parts if typ == "optional"]
    mandatory = [expr for typ, expr in tsquery_parts if typ == "mandatory"]
    excluded = [expr for typ, expr in tsquery_parts if typ == "excluded"]

    query_parts = []
    if optional:
        or_expr = " || ' | ' || ".join(optional)
        if len(optional) > 1:
            query_parts.append(f"'(' || {or_expr} || ')'")
        else:
            query_parts.append(or_expr)
    for expr in mandatory:
        query_parts.append(f"'(' || {expr} || ')'")
    for expr in excluded:
        query_parts.append(f"'!(' || {expr} || ')'")

    combined_tsquery = " || ' & ' || ".join(query_parts)

    # Parse the original input as-is for prefix matching (like "search" operator)
    original_parsed = parse_search_input(value)

    if original_parsed:
        # OR between original prefix match and fuzzy-corrected match
        sql_expr = (
            f"({tablename}.{column_name} @@ to_tsquery('{pg_language}', unaccent(:_original_search))"
            f" OR "
            f"{tablename}.{column_name} @@ to_tsquery('{pg_language}', unaccent({combined_tsquery})))"
        )
        bind_params["_original_search"] = original_parsed
    else:
        sql_expr = f"{tablename}.{column_name} @@ to_tsquery('{pg_language}', unaccent({combined_tsquery}))"

    return text(sql_expr).bindparams(**bind_params)


def _collect_fulltext_search_rules(
    filters: Filter | None,
) -> dict[str, list[str]]:
    """
    Collect all fulltext search rules from parsed filters.
    Returns dict mapping field_name to list of parsed tsquery strings.
    """
    result: dict[str, list[str]] = {}

    if filters is None:
        return result

    if isinstance(filters, FilterRule):
        if filters.operator in ("search", "search_fuzzy") and filters.value:
            parsed = parse_search_input(filters.value)
            if parsed:
                result.setdefault(filters.field, []).append(parsed)
        return result

    if isinstance(filters, FilterCondition):
        for rule in filters.rules:
            for field_name, tsqueries in _collect_fulltext_search_rules(rule).items():
                result.setdefault(field_name, []).extend(tsqueries)

    return result


def _add_fulltext_rank_extra_select(query: QuerySet, filters: Filter | None) -> QuerySet:
    """
    Scan filters for fulltext search operators and add ts_rank() as extra_select.
    This makes the rank available for ordering via inject_order_by().
    """
    search_rules = _collect_fulltext_search_rules(filters)

    if not search_rules:
        return query

    locale = _get_fulltext_locale()
    pg_language = get_pg_language(locale)

    for field_path, tsqueries in search_rules.items():
        target_cls, tablename, field_name = _resolve_fulltext_field(query.model_class, field_path)
        column_name = f"{field_name}_{locale}"
        qualified_column = f"{tablename}.{column_name}"
        label_name = f"_{field_path}_rank"

        # Combine multiple tsqueries with || (OR) for ranking
        if len(tsqueries) == 1:
            combined_tsquery = tsqueries[0]
        else:
            combined_tsquery = " || ".join(f"to_tsquery('{pg_language}', unaccent('{tq}'))" for tq in tsqueries)

        try:
            if len(tsqueries) == 1:
                rank_expr = literal_column(
                    f"ts_rank({qualified_column}, to_tsquery('{pg_language}', unaccent('{combined_tsquery}')))"
                ).label(label_name)
            else:
                rank_expr = literal_column(f"ts_rank({qualified_column}, {combined_tsquery})").label(label_name)
        except Exception:
            # Fallback without unaccent
            if len(tsqueries) == 1:
                rank_expr = literal_column(
                    f"ts_rank({qualified_column}, to_tsquery('{pg_language}', '{combined_tsquery}'))"
                ).label(label_name)
            else:
                combined_no_unaccent = " || ".join(f"to_tsquery('{pg_language}', '{tq}')" for tq in tsqueries)
                rank_expr = literal_column(f"ts_rank({qualified_column}, {combined_no_unaccent})").label(label_name)

        query = cast(QuerySet, query.extra_select(cast(Any, rank_expr)))

    return query


def _build_generic_reference_expression(model_cls: type[Model], generic_field: Any, filters: FilterRule) -> Any:
    """Filter on a GenericForeignKey field itself: references are ``[model, id]``
    pairs (or ``{model, id}`` objects), compiled onto the underlying column pair
    (``in`` groups the ids per target model)."""
    model_col = model_cls.table.columns[generic_field.model_column]
    id_col = model_cls.table.columns[generic_field.id_column]
    operator = filters.operator
    value = filters.value

    def _pair(reference: Any) -> tuple[Any, Any]:
        if not isinstance(reference, (list, tuple)) or len(reference) != 2:
            raise InvalidFilterError(
                f"Filter value for '{filters.field}' must be a [model, id] pair, got {reference!r}"
            )
        try:
            decomposed = generic_field._decompose({"model": reference[0], "id": reference[1]})
        except ValueError as e:
            raise InvalidFilterError(str(e))
        return decomposed[generic_field.model_column], decomposed[generic_field.id_column]

    if operator in ("=", "!="):
        model_name, record_id = _pair(value)
        expression = sa_and(model_col == model_name, id_col == record_id)
        return expression if operator == "=" else sa_not(expression)

    if operator in ("in", "not in"):
        if not isinstance(value, (list, tuple)):
            raise InvalidFilterError(f"Operator '{operator}' on '{filters.field}' requires a list of references")

        ids_by_model: dict[Any, list[Any]] = {}
        for reference in value:
            model_name, record_id = _pair(reference)
            ids_by_model.setdefault(model_name, []).append(record_id)

        if not ids_by_model:
            raise InvalidFilterError(f"Operator '{operator}' on '{filters.field}' requires at least one reference")

        expression = sa_or(
            *(sa_and(model_col == model_name, id_col.in_(ids)) for model_name, ids in ids_by_model.items())
        )
        return expression if operator == "in" else sa_not(expression)

    if operator == "is empty":
        return id_col.is_(None)

    if operator == "is not empty":
        return id_col.is_not(None)

    raise InvalidFilterError(f"Operator '{operator}' is not supported on the reference field '{filters.field}'")


def _path_crosses_generic_relation(model_cls: type[Model], field_path: str) -> bool:
    current_model = model_cls

    for part in field_path.split(".")[:-1]:
        field_info = current_model.meta.fields.get(part)
        if field_info is None:
            return False
        if getattr(field_info, "is_generic_related", False):
            return True
        if hasattr(field_info, "related_model"):
            current_model = getattr(field_info, "related_model")
        elif hasattr(field_info, "target"):
            current_model = getattr(field_info, "target")
        elif hasattr(field_info, "related_from"):
            current_model = getattr(field_info, "related_from")
        else:
            return False

    return False


def _resolve_generic_pair_column(model_cls: type[Model], field_path: str) -> Any | None:
    pair = resolve_generic_pair(model_cls, field_path)
    if pair is None:
        return None

    generic_field, side = pair
    column_name = generic_field.model_column if side == "model" else generic_field.id_column
    return model_cls.table.columns[column_name]


def _find_field_type_in_model(model_cls: type[Model], field_path: str) -> type[BaseFieldType]:
    """
    Recursively find a field type in a model by its field path.
    Virtual generic pair paths (``<field>.$model`` / ``<field>.id``) resolve to
    the underlying column field.

    Args:
        model_cls: The model class to search in
        field_path: The field path (e.g. 'contact.company.name')

    Returns:
        The column object

    Raises:
        InvalidFilterError: If the field path is invalid
    """
    generic_pair = resolve_generic_pair(model_cls, field_path)
    if generic_pair is not None:
        generic_field, side = generic_pair
        column_name = generic_field.model_column if side == "model" else generic_field.id_column
        return cast(Any, model_cls.meta.fields[column_name])

    field_parts = field_path.split(".")
    current_model = model_cls

    for i, part in enumerate(field_parts):
        if i == 0 and part.startswith("extra_"):
            from fastedgy.models.workspace_extra_field import EXTRA_FIELDS_MAP
            from fastedgy.metadata_model.generator import generate_metadata_name
            from fastedgy import context

            if "extra" in model_cls.meta.fields:
                extra_field_name = part[6:]
                extra_fields = context.get_map_workspace_extra_fields(generate_metadata_name(current_model))

                if extra_field_name in extra_fields:
                    extra_field = extra_fields[extra_field_name]

                    if extra_field.field_type is not None:
                        field_type = EXTRA_FIELDS_MAP.get(extra_field.field_type)

                        if field_type:
                            return field_type

            raise InvalidFilterError(f"Field '{part}' not found in model {current_model.__name__}")
        elif i == len(field_parts) - 1:
            fields = current_model.meta.fields

            if part in fields:
                return fields.get(part)
            else:
                raise InvalidFilterError(f"Field '{part}' not found in model {current_model.__name__}")
        else:
            if part not in current_model.meta.fields:
                raise InvalidFilterError(f"Field '{part}' not found in model {current_model.__name__}")

            field_info = current_model.meta.fields[part]

            if hasattr(field_info, "related_model"):
                current_model = getattr(field_info, "related_model")
            elif hasattr(field_info, "target"):
                current_model = getattr(field_info, "target")
            elif hasattr(field_info, "related_from"):
                current_model = getattr(field_info, "related_from")
            else:
                raise InvalidFilterError(f"Field '{part}' is not a relationship field")

    raise InvalidFilterError(f"Field '{field_path}' not found")


def _find_column_in_model(model_cls: type[Model], field_path: str) -> Any:
    """
    Recursively find a column in a model by its field path.

    Args:
        model_cls: The model class to search in
        field_path: The field path (e.g. 'contact.company.name')

    Returns:
        The column object

    Raises:
        InvalidFilterError: If the field path is invalid
    """
    generic_column = _resolve_generic_pair_column(model_cls, field_path)
    if generic_column is not None:
        return generic_column

    field_parts = field_path.split(".")
    current_model = model_cls

    for i, part in enumerate(field_parts):
        if i == 0 and part.startswith("extra_"):
            from fastedgy.models.workspace_extra_field import EXTRA_FIELDS_MAP
            from fastedgy.metadata_model.generator import generate_metadata_name
            from fastedgy import context

            if "extra" in model_cls.meta.fields:
                extra_field_name = part[6:]
                extra_fields = context.get_map_workspace_extra_fields(generate_metadata_name(current_model))

                if extra_field_name in extra_fields:
                    extra_field = extra_fields[extra_field_name]

                    if extra_field.field_type is not None:
                        field_type = EXTRA_FIELDS_MAP.get(extra_field.field_type)

                        if field_type:
                            return model_cls.columns.extra.op("->>")(extra_field_name)

            raise InvalidFilterError(f"Field '{part}' not found in model {current_model.__name__}")
        elif i == len(field_parts) - 1:
            columns = current_model.table.columns

            if hasattr(columns, part):
                return columns[part]
            else:
                raise InvalidFilterError(f"Field '{part}' not found in model {current_model.__name__}")
        else:
            if part not in current_model.meta.fields:
                raise InvalidFilterError(f"Field '{part}' not found in model {current_model.__name__}")

            field_info = current_model.meta.fields[part]

            if hasattr(field_info, "related_model"):
                current_model = getattr(field_info, "related_model")
            elif hasattr(field_info, "target"):
                current_model = getattr(field_info, "target")
            elif hasattr(field_info, "related_from"):
                current_model = getattr(field_info, "related_from")
            else:
                raise InvalidFilterError(f"Field '{part}' is not a relationship field")

    raise InvalidFilterError(f"Field '{field_path}' not found")


def _convert_value_by_field_type(model_cls: type[Model], field_path: str, value: Any) -> Any:
    """
    Converts a value based on the field type.

    Args:
        model_cls: The model class to search in
        field_path: The field path (e.g. 'contact.company.name')
        value: The value to convert

    Returns:
        The converted value
    """
    field = None
    parts = field_path.split(".")
    current_cls = model_cls

    for part in parts:
        if field_path.startswith("extra_"):
            from fastedgy.metadata_model.generator import generate_metadata_name
            from fastedgy import context
            from fastedgy.models.workspace_extra_field import (
                EXTRA_FIELDS_MAP,
                EXTRA_FIELD_TYPE_OPTIONS,
            )

            extra_field_name = field_path[6:]
            extra_fields = context.get_map_workspace_extra_fields(generate_metadata_name(model_cls))

            if extra_field_name in extra_fields:
                extra_field = extra_fields[extra_field_name]

                if extra_field.field_type is not None:
                    field_type = EXTRA_FIELDS_MAP.get(extra_field.field_type)

                    if field_type:
                        field = field_type(**EXTRA_FIELD_TYPE_OPTIONS[extra_field.field_type])
        else:
            field = current_cls.meta.fields.get(part)
            if not field:
                return value  # Field not found, return value as-is

        if field and hasattr(field, "target"):
            current_cls = field.target
        elif field and hasattr(field, "related_from"):
            current_cls = field.related_from

    if isinstance(field, (DateField, DateTimeField)):
        from datetime import datetime

        return _convert_value(value, lambda val: datetime.fromisoformat(val.replace("Z", "+00:00")))
    elif isinstance(field, IntegerField):
        return _convert_value(value, lambda val: int(val))
    elif isinstance(field, (FloatField, DecimalField)):
        return _convert_value(value, lambda val: float(val))

    return value


__all__ = [
    "build_filter_expression",
    "filter_query",
]
