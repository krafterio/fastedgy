# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from abc import ABC, abstractmethod

from email.message import EmailMessage


class MailAdapter(ABC):
    """Transport responsible for delivering a prepared email message."""

    @abstractmethod
    async def deliver(self, email: EmailMessage) -> None: ...


__all__ = [
    "MailAdapter",
]
