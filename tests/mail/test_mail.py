# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from email.message import EmailMessage

import pytest

from fastedgy.app import FastEdgy
from fastedgy.dependencies import get_service
from fastedgy.mail import Mail, MockAdapter, SmtpAdapter


def _message(to: str) -> EmailMessage:
    email = EmailMessage()
    email["To"] = to
    email["Subject"] = "Hello"
    email.set_content("Body")

    return email


async def test_mock_adapter_records_and_inspects_messages() -> None:
    adapter = MockAdapter()

    await adapter.deliver(_message("a@example.io"))

    assert adapter.count == 1
    assert adapter.last is not None
    assert adapter.was_sent_to("a@example.io")
    assert adapter.messages_to("nobody@example.io") == []

    adapter.clear()

    assert adapter.count == 0


def test_smtp_adapter_requires_a_host() -> None:
    with pytest.raises(ValueError):
        SmtpAdapter(host="", port=587, username="user", password="pass")


async def test_mail_uses_the_mock_adapter_in_tests(setup_db: FastEdgy) -> None:
    assert isinstance(get_service(Mail).adapter, MockAdapter)


async def test_mail_send_delivers_through_the_adapter(setup_db: FastEdgy) -> None:
    mail = get_service(Mail)
    adapter = mail.adapter

    assert isinstance(adapter, MockAdapter)

    adapter.clear()
    await mail.send(_message("someone@example.io"))

    assert adapter.count == 1
    assert adapter.was_sent_to("someone@example.io")
