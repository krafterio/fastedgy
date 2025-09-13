# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from typing import TYPE_CHECKING

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from fastedgy.context import set_locale
from fastedgy.config import BaseSettings
from fastedgy.dependencies import get_service

if TYPE_CHECKING:
    from fastedgy.app import FastEdgy


class LocaleMiddleware(BaseHTTPMiddleware):
    """Middleware to parse Accept-Language header and set locale in context."""

    def __init__(self, app: "FastEdgy"):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        settings = get_service(BaseSettings)
        locale = self._determine_locale(request, settings)

        set_locale(locale)

        try:
            return await call_next(request)
        finally:
            pass

    def _determine_locale(self, request: Request, settings: BaseSettings) -> str:
        """Determine the best locale from Accept-Language header."""
        accept_language = request.headers.get("accept-language")

        if not accept_language:
            return settings.fallback_locale

        preferred_locales = self._parse_accept_language(accept_language)

        for locale, _ in preferred_locales:
            if locale in settings.available_locales:
                return locale

            language = locale.split('-')[0]

            if language in settings.available_locales:
                return language

        return settings.fallback_locale

    def _parse_accept_language(self, header: str) -> list[tuple[str, float]]:
        """Parse Accept-Language header and return ordered list of (locale, quality)."""
        locales = []

        for item in header.split(','):
            parts = item.strip().split(';q=')
            locale = parts[0].strip()
            quality = 1.0 if len(parts) == 1 else float(parts[1])
            locales.append((locale, quality))

        return sorted(locales, key=lambda x: x[1], reverse=True)


__all__ = [
    "LocaleMiddleware",
]
