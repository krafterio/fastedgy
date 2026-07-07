# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.dependencies import Inject, get_service, unregister_service


class _UnregisteredConfig:
    max_workers: int = 7


class _Manager:
    def __init__(self, config: _UnregisteredConfig = Inject(_UnregisteredConfig)):
        self.config = config


def test_inject_default_resolves_unregistered_type() -> None:
    try:
        manager = get_service(_Manager)

        assert isinstance(manager.config, _UnregisteredConfig)
        assert manager.config.max_workers == 7
    finally:
        unregister_service(_Manager)
        unregister_service(_UnregisteredConfig)
