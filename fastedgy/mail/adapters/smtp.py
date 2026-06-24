# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import logging

from email.message import EmailMessage

import aiosmtplib

from fastedgy.mail.adapters.base import MailAdapter


logger = logging.getLogger("services.mail")


class SmtpAdapter(MailAdapter):
    """Deliver emails through an SMTP server."""

    def __init__(self, host: str, port: int, username: str, password: str, use_tls: bool = True) -> None:
        if not host:
            raise ValueError("SMTP host is not configured")

        if not port:
            raise ValueError("SMTP port is not configured")

        if not username:
            raise ValueError("SMTP username is not configured")

        if not password:
            raise ValueError("SMTP password is not configured")

        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.use_tls = use_tls

    async def deliver(self, email: EmailMessage) -> None:
        recipients = email.get("To", "")
        logger.debug(f"Sending email to {recipients}")

        smtp = aiosmtplib.SMTP(
            hostname=self.host,
            port=self.port,
            start_tls=self.use_tls,
            username=self.username,
            password=self.password,
        )

        try:
            await smtp.connect()
            await smtp.send_message(email)
            logger.debug(f"Email sent successfully to {recipients}")
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            raise
        finally:
            smtp.close()


__all__ = [
    "SmtpAdapter",
]
