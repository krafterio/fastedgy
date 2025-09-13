# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.dependencies import get_service


def _t(message: str, **kwargs) -> str:
    """
    Translate a message using the current locale.

    Usage:
        from fastedgy import _t

        # Simple translation
        translated = _t("Hello world")

        # Translation with parameters
        translated = _t("Hello {name}", name="John")
    """
    from fastedgy.i18n.service import I18n

    try:
        i18n = get_service(I18n)

        return i18n._(message, **kwargs)
    except Exception:
        try:
            return message.format(**kwargs) if kwargs else message
        except KeyError:
            return message


__all__ = [
    "_t",
]
