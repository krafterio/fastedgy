# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from datetime import UTC, datetime


def datetime_serializer(value: datetime) -> str:
    """
    Serialize datetime with timezone from the current request context.

    For legacy compatibility, this ensures datetime values are returned
    with the appropriate timezone offset instead of UTC.

    Args:
        value: The datetime to serialize

    Returns:
        ISO 8601 string with timezone offset (e.g., "2025-10-04T19:00:00+02:00")
    """

    from fastedgy.context import get_timezone, has_timezone

    if not isinstance(value, datetime):
        return value

    tz = get_timezone()

    if value.tzinfo is not None:
        value = value.astimezone(tz)
    else:
        value = value.replace(tzinfo=UTC).astimezone(tz)

    if not has_timezone():
        return value.replace(tzinfo=None).isoformat()

    return value.isoformat()


__all__ = [
    "datetime_serializer",
]
