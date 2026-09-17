import re

from fastedgy.config import BaseSettings


def _settings(origins: str | None) -> BaseSettings:
    settings = BaseSettings()
    settings.cors_allow_origins = origins

    return settings


def test_allows_every_origin_without_configuration():
    settings = _settings(None)

    assert settings.cors_origins == ["*"]
    assert settings.cors_origin_regex is None


def test_keeps_the_exact_origins_apart_from_the_patterns():
    settings = _settings("https://app.example.com, http://localhost:*")

    assert settings.cors_origins == ["https://app.example.com"]
    assert settings.cors_origin_regex == r"http://localhost:.*"


def test_matches_any_port_of_a_pattern():
    regex = _settings("http://localhost:*,http://127.0.0.1:*").cors_origin_regex

    assert regex is not None
    assert re.fullmatch(regex, "http://localhost:8089")
    assert re.fullmatch(regex, "http://127.0.0.1:5173")
    assert not re.fullmatch(regex, "http://localhostile:8089")
    assert not re.fullmatch(regex, "https://evil.com")
