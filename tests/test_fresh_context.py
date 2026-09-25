# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy import context
from fastedgy.app import FastEdgy
from fastedgy.test.factories import make_request


async def test_a_test_leaves_a_request_behind(setup_app: FastEdgy) -> None:
    context.set_request(make_request())


async def test_the_next_test_starts_without_it(setup_app: FastEdgy) -> None:
    assert context.get_request() is None
