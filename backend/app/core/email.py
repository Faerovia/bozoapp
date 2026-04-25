"""
Email sending abstrakce — pluggable backend.

Třídy:
- `EmailSender` (Protocol) — interface
- `ConsoleEmailSender` — dev; loguje email do stdout.
- `NullEmailSender` — testy (silent drop).
- `SmtpEmailSender` — produkce; generický SMTP přes `aiosmtplib` (async).

Switch logika v `get_email_sender()`:
- env=test → NullEmailSender
- SMTP_HOST set → SmtpEmailSender
- jinak → ConsoleEmailSender
"""
from __future__ import annotations

import logging
import ssl
from dataclasses import dataclass
from email.message import EmailMessage as StdEmailMessage
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class EmailAttachment:
    filename: str
    content: bytes
    mime_type: str = "application/octet-stream"


@dataclass
class EmailMessage:
    to: str
    subject: str
    body_text: str
    body_html: str | None = None
    attachments: list[EmailAttachment] | None = None


class EmailSender(Protocol):
    async def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailSender:
    """Default pro dev. Email pouze loguje — nikam nejde. Vidět v console logu."""

    async def send(self, message: EmailMessage) -> None:
        log.info(
            "[ConsoleEmailSender] TO=%s SUBJECT=%r\n---BODY---\n%s\n---END---",
            message.to, message.subject, message.body_text,
        )


class NullEmailSender:
    """Pro testy — silent drop. Test může přepsat fixture na MagicMock/spy."""

    async def send(self, message: EmailMessage) -> None:
        return None


class SmtpEmailSender:
    """
    Generický SMTP klient. Funguje proti Gmail, Seznam, Postmark SMTP,
    SendGrid SMTP relay, Mailgun, SES SMTP — stačí nastavit SMTP_HOST/PORT/
    USER/PASS v env. STARTTLS je default (port 587); pro implicit TLS
    (port 465) nastav `smtp_tls=False` (není to negace, jen jinak pojmenované —
    oba módy šifrují, jen v různém pořadí handshakeu).

    Používá stdlib `smtplib` spuštěný v threadpool executoru — aiosmtplib
    bychom museli přidat jako dep, ale pro občasné emaily (password reset,
    2FA enroll) je blocking SMTP call v executoru postačující.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        user: str,
        password: str,
        from_addr: str,
        use_starttls: bool = True,
    ) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.from_addr = from_addr
        self.use_starttls = use_starttls

    async def send(self, message: EmailMessage) -> None:
        import asyncio

        def _send_blocking() -> None:
            import smtplib

            msg = StdEmailMessage()
            msg["From"] = self.from_addr
            msg["To"] = message.to
            msg["Subject"] = message.subject
            msg.set_content(message.body_text)
            if message.body_html:
                msg.add_alternative(message.body_html, subtype="html")
            if message.attachments:
                for att in message.attachments:
                    maintype, _, subtype = att.mime_type.partition("/")
                    msg.add_attachment(
                        att.content,
                        maintype=maintype or "application",
                        subtype=subtype or "octet-stream",
                        filename=att.filename,
                    )

            context = ssl.create_default_context()

            if self.use_starttls:
                with smtplib.SMTP(self.host, self.port, timeout=15) as server:
                    server.ehlo()
                    server.starttls(context=context)
                    server.ehlo()
                    if self.user:
                        server.login(self.user, self.password)
                    server.send_message(msg)
            else:
                with smtplib.SMTP_SSL(
                    self.host, self.port, context=context, timeout=15
                ) as server:
                    if self.user:
                        server.login(self.user, self.password)
                    server.send_message(msg)

        try:
            await asyncio.to_thread(_send_blocking)
        except Exception:
            log.exception(
                "SMTP send failed (to=%s, subject=%r)",
                message.to, message.subject,
            )
            # Propagujeme výjimku výš — caller (password reset, 2FA) by měl
            # zareagovat. Alternativně by šel soft-fail, ale pro bezpečnostní
            # email bychom to neměli skrývat.
            raise


# ── Factory ──────────────────────────────────────────────────────────────────
_sender: EmailSender | None = None


def get_email_sender() -> EmailSender:
    """Vrátí singleton EmailSender. Switch podle env konfigurace."""
    global _sender
    if _sender is not None:
        return _sender

    settings = get_settings()

    if settings.environment == "test":
        _sender = NullEmailSender()
    elif settings.smtp_host:
        _sender = SmtpEmailSender(
            host=settings.smtp_host,
            port=settings.smtp_port,
            user=settings.smtp_user,
            password=settings.smtp_password,
            from_addr=settings.smtp_from,
            use_starttls=settings.smtp_tls,
        )
    else:
        # SMTP není nakonfigurován (dev bez SMTP) — log-only sender
        _sender = ConsoleEmailSender()

    return _sender


def reset_email_sender() -> None:
    """Pro testy — reset singletonu aby šel injectnout mock."""
    global _sender
    _sender = None
