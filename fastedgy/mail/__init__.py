# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.mail.adapters import MailAdapter, MockAdapter, SmtpAdapter
from fastedgy.mail.service import Mail, TemplatePart, clean_markdown_residuals

__all__ = [
    "Mail",
    "MailAdapter",
    "MockAdapter",
    "SmtpAdapter",
    "TemplatePart",
    "clean_markdown_residuals",
]
