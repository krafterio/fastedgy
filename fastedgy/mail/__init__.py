# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

from fastedgy.mail.service import Mail, TemplatePart, clean_markdown_residuals
from fastedgy.mail.adapters import MailAdapter, MockAdapter, SmtpAdapter


__all__ = [
    "Mail",
    "TemplatePart",
    "clean_markdown_residuals",
    "MailAdapter",
    "MockAdapter",
    "SmtpAdapter",
]
