# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from email.message import EmailMessage

from fastedgy.mail.adapters.base import MailAdapter


class MockAdapter(MailAdapter):
    """In-memory adapter that records messages instead of sending them.

    Useful in tests: messages are kept in ``sent`` and can be inspected through
    the helper accessors below.
    """

    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []

    async def deliver(self, email: EmailMessage) -> None:
        self.sent.append(email)

    @property
    def count(self) -> int:
        return len(self.sent)

    @property
    def last(self) -> EmailMessage | None:
        return self.sent[-1] if self.sent else None

    def clear(self) -> None:
        self.sent.clear()

    def messages_to(self, recipient: str) -> list[EmailMessage]:
        return [email for email in self.sent if recipient in (email.get("To") or "")]

    def was_sent_to(self, recipient: str) -> bool:
        return bool(self.messages_to(recipient))


__all__ = [
    "MockAdapter",
]
