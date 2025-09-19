# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.i18n.service import TranslatableString


def _t(message: str, **kwargs) -> TranslatableString:
    """
    Translate a message using the current locale.

    Usage:
        from fastedgy import _t

        # Simple translation
        translated = _t("Hello world")

        # Translation with parameters
        translated = _t("Hello {name}", name="John")
    """
    return TranslatableString(message, **kwargs)


_ = _t


__all__ = [
    "_t",
    "_",
]
