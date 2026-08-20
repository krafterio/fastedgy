# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.mail.adapters.base import MailAdapter
from fastedgy.mail.adapters.mock import MockAdapter
from fastedgy.mail.adapters.smtp import SmtpAdapter

__all__ = [
    "MailAdapter",
    "MockAdapter",
    "SmtpAdapter",
]
