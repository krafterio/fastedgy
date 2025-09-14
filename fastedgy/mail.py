# Copyright Krafter SAS <developer@krafter.io>
# MIT License (see LICENSE file).

import aiosmtplib

import logging

import html2text

import os

import re

from email.message import EmailMessage

from enum import Enum

from fastedgy.dependencies import get_service, register_service
from fastedgy.storage import BaseSettings

from jinja2 import Environment, FileSystemLoader, Undefined, select_autoescape


logger = logging.getLogger("services.mail")


class TemplatePart(Enum):
    SUBJECT = "subject"
    BODY_HTML = "body_html"
    BODY_TEXT = "body_text"


class Mail:
    """Service to send emails"""

    def __init__(self, settings: BaseSettings):
        if not settings.smtp_host:
            logger.error("SMTP host is not configured")
            raise ValueError("SMTP host is not configured")

        if not settings.smtp_port:
            logger.error("SMTP port is not configured")
            raise ValueError("SMTP port is not configured")

        if not settings.smtp_username:
            logger.error("SMTP username is not configured")
            raise ValueError("SMTP username is not configured")

        if not settings.smtp_password:
            logger.error("SMTP password is not configured")
            raise ValueError("SMTP password is not configured")

        if not settings.smtp_default_from:
            logger.error("SMTP default from is not configured")
            raise ValueError("SMTP default from is not configured")

        self.settings = settings
        self.jinja_env = Environment(
            loader=FileSystemLoader(self._template_path),
            autoescape=select_autoescape(["html", "xml"]),
            undefined=SilentUndefined,
            trim_blocks=True,
            lstrip_blocks=True,
        )

        self.html_converter = html2text.HTML2Text()
        self.html_converter.ignore_links = True
        self.html_converter.ignore_images = True
        self.html_converter.ignore_emphasis = True
        self.html_converter.ignore_tables = True
        self.html_converter.body_width = 0
        self.html_converter.unicode_snob = True
        self.html_converter.protect_links = False

    @property
    def _template_path(self) -> str:
        return self.settings.mail_template_path

    def render_template(
        self,
        template_name: str,
        tpl_part: TemplatePart,
        context: dict,
        strict: bool = False,
    ) -> str | None:
        logger.debug(f"Rendering template {template_name}, part {tpl_part.value}")
        template = self.jinja_env.get_template(template_name)

        if tpl_part.value not in template.blocks:
            if strict:
                logger.error(
                    f"Template '{template_name}' is missing required '{tpl_part.value}' block"
                )
                raise ValueError(
                    f"Template '{template_name}' is missing required '{tpl_part.value}' block"
                )

            logger.warning(
                f"Template '{template_name}' doesn't have '{tpl_part.value}' block"
            )
            return None

        tpl_context = template.new_context(context)
        block = template.blocks[tpl_part.value]

        return "".join(block(tpl_context)).strip() or None

    async def generate_email_template(
        self, template_name: str, tpl_vals: dict, email_parts: EmailMessage | dict
    ) -> EmailMessage:
        logger.debug(f"Generating email from template {template_name}")
        if isinstance(email_parts, dict):
            email = EmailMessage()
            for key, value in email_parts.items():
                email[key] = value
        else:
            email = email_parts

        subject: str | None = self.render_template(
            template_name, TemplatePart.SUBJECT, tpl_vals
        )
        html_content: str | None = self.render_template(
            template_name, TemplatePart.BODY_HTML, tpl_vals
        )
        text_content: str | None = self.render_template(
            template_name, TemplatePart.BODY_TEXT, tpl_vals
        )

        if not text_content and html_content:
            logger.debug("Converting HTML content to text")
            markdown_text = self.html_converter.handle(html_content)
            text_content = clean_markdown_residuals(markdown_text)

        email.make_alternative()

        if subject:
            email["Subject"] = subject

        if text_content:
            email.add_alternative(text_content, subtype="plain")

        if html_content:
            email.add_alternative(html_content, subtype="html")

        return email

    async def send_template(
        self, template_name: str, tpl_vals: dict, email_parts: EmailMessage | dict
    ) -> None:
        logger.debug(f"Sending email using template {template_name}")
        email = await self.generate_email_template(template_name, tpl_vals, email_parts)
        await self.send(email)

    async def send(self, email: EmailMessage) -> None:
        if not email["From"]:
            email["From"] = self.settings.smtp_default_from

        recipients = email.get("To", "")
        logger.debug(f"Sending email to {recipients}")

        try:
            await aiosmtplib.send(
                email,
                hostname=self.settings.smtp_host,
                port=self.settings.smtp_port,
                start_tls=self.settings.smtp_use_tls,
                username=self.settings.smtp_username,
                password=self.settings.smtp_password,
            )
            logger.debug(f"Email sent successfully to {recipients}")
        except Exception as e:
            logger.error(f"Failed to send email: {str(e)}")
            raise


class SilentUndefined(Undefined):
    def __getattr__(self, name):
        return self

    def __getitem__(self, key):
        return self

    def __str__(self):
        return ""


def clean_markdown_residuals(text: str) -> str:
    """Cleans residual Markdown characters from text"""
    # Remove # characters from headings
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    # Remove * and _ characters for emphasis
    text = re.sub(r"([*_]{1,2})(\S.*?\S|[^\s])\1", r"\2", text)
    # Remove ` characters for code
    text = re.sub(r"`([^`]*)`", r"\1", text)
    # Remove > characters for blockquotes
    text = re.sub(r"^>\s*", "", text, flags=re.MULTILINE)
    # Remove [] and () characters for links
    text = re.sub(r"\[(.*?)\]\(.*?\)", r"\1", text)
    # Remove horizontal separators
    text = re.sub(r"^-{3,}$", "", text, flags=re.MULTILINE)

    # Preserve list bullets and numbers, but format them properly
    # Transform "- Item" to "• Item"
    text = re.sub(r"^\s*[-*+]\s+", "• ", text, flags=re.MULTILINE)
    # Keep list numbers as is, "1. Item" remains "1. Item"

    return text


register_service(lambda: Mail(get_service(BaseSettings)), Mail)


__all__ = [
    "Mail",
    "TemplatePart",
    "clean_markdown_residuals",
]
