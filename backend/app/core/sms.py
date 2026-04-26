"""
SMS sending abstrakce — pluggable backend.

Třídy:
- `SmsSender` (Protocol) — interface
- `ConsoleSmsSender` — dev; loguje SMS do stdout
- `NullSmsSender` — testy (silent drop)
- `SmartSmsSender` — produkce; SmartSMS.cz (CZ provider, jednoduché REST API)
- (Twilio / BulkSMS / SmsBrana lze přidat jako další implementace)

Switch v `get_sms_sender()`:
- env=test → NullSmsSender
- SMS_PROVIDER=smartsms + creds → SmartSmsSender
- jinak → ConsoleSmsSender
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol

from app.core.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class SmsMessage:
    to: str  # telefonní číslo v E.164 (+420...) nebo lokálně
    body: str


class SmsSender(Protocol):
    async def send(self, message: SmsMessage) -> None: ...


class ConsoleSmsSender:
    """Default pro dev. SMS pouze loguje — nikam nejde."""

    async def send(self, message: SmsMessage) -> None:
        log.info(
            "[ConsoleSmsSender] TO=%s BODY=%r",
            message.to, message.body,
        )


class NullSmsSender:
    """Pro testy — silent drop."""

    async def send(self, message: SmsMessage) -> None:
        return None


class SmartSmsSender:
    """
    SmartSMS.cz — český provider, REST API, ~1.30 Kč / SMS.
    https://www.smartsms.cz/dokumentace-api/

    Konfigurace přes env: SMS_API_TOKEN. Číslo se posílá v formátu +420xxx.
    """

    def __init__(self, *, api_token: str, sender_id: str = "DigitalOZO") -> None:
        self.api_token = api_token
        self.sender_id = sender_id

    async def send(self, message: SmsMessage) -> None:
        import asyncio
        import urllib.parse
        import urllib.request

        def _send_blocking() -> None:
            params = urllib.parse.urlencode({
                "username": "",  # SmartSMS používá token-only auth
                "password": self.api_token,
                "to": message.to,
                "message": message.body,
                "sender": self.sender_id,
            })
            url = f"https://api.smartsms.cz/sms/send?{params}"
            req = urllib.request.Request(url, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    body = resp.read().decode("utf-8")
                    log.info("SmartSMS response: %s", body[:200])
            except Exception:
                log.exception("SmartSMS send failed (to=%s)", message.to)
                raise

        await asyncio.to_thread(_send_blocking)


_sender: SmsSender | None = None


def get_sms_sender() -> SmsSender:
    global _sender
    if _sender is not None:
        return _sender

    settings = get_settings()

    if settings.environment == "test":
        _sender = NullSmsSender()
    elif settings.sms_provider == "smartsms" and settings.sms_api_token:
        _sender = SmartSmsSender(
            api_token=settings.sms_api_token,
            sender_id=settings.sms_sender_id or "DigitalOZO",
        )
    else:
        _sender = ConsoleSmsSender()

    return _sender


def reset_sms_sender() -> None:
    """Pro testy — reset singletonu."""
    global _sender
    _sender = None
