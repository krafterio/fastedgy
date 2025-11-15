# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.i18n.service import TranslatableString


def _ts(message: str, **kwargs) -> TranslatableString:
    """
    Translate a message using the current locale.

    Usage:
        from fastedgy import _ts

        # Simple translation
        translated: TranslatableString = _ts("Hello world")

        # Translation with parameters
        translated: TranslatableString = _ts("Hello {name}", name="John")
    """
    return TranslatableString(message, **kwargs)


def _t(message: str, **kwargs) -> str:
    """
    Translate a message using the current locale and return it as a string immediately.

    Usage:
        from fastedgy import _t

        # Simple translation
        translated: str = _t("Hello world")

        # Translation with parameters
        translated: str = _t("Hello {name}", name="John")
    """
    return str(TranslatableString(message, **kwargs))


_ = _t


__all__ = [
    "_ts",
    "_t",
    "_",
]
