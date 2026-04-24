"""
Email sending abstrakce — pluggable backend.

Třídy:
- `EmailSender` (Protocol) — interface
- `ConsoleEmailSender` — default; loguje email do stdout. Pro dev / CI.
- `NullEmailSender` — pro testy (silent drop).

Produkční implementace (SMTP, Postmark, SendGrid, SES) přidáme později jako
nové třídy; endpointy je budou používat přes `get_email_sender()` dependency.

Proč Protocol a ne abc.ABC: Protocol umožňuje duck-typing, Test může dát
MagicMock aniž by dědil z abstract class.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    to: str
    subject: str
    body_text: str
    body_html: str | None = None


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


# ── Factory ──────────────────────────────────────────────────────────────────
# Zatím jen jeden sender; až přijde produkční SMTP, přepni podle env.
_sender: EmailSender | None = None


def get_email_sender() -> EmailSender:
    """Vrátí singleton EmailSender. V testu env → NullEmailSender."""
    global _sender
    if _sender is None:
        settings = get_settings()
        if settings.environment == "test":
            _sender = NullEmailSender()
        else:
            # Production path zatím padá do console loggeru — skutečný SMTP
            # nasadíme v samostatném commitu, až bude k dispozici mail infra.
            _sender = ConsoleEmailSender()
    return _sender
