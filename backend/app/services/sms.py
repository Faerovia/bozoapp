"""SMS gateway abstrakce.

V dev/demo módu posílá mock — pouze loguje a vrací úspěch. Skutečné SMS
budou napojené přes SMSbrána.cz nebo Twilio později (jen swap implementace
SmsSender, žádné změny v callers).

Konfigurace přes settings:
- SMS_DEV_MODE=true → MockSmsSender (loguje, vrací success)
- SMS_DEV_MODE=false → real provider (TBD)

V dev mode je OTP kód vždy '111111' (zjednodušení demo flow). Toto je
zakódováno v signatures service při generování — sender se to nedozví,
jen pošle to, co dostane.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import get_settings

log = logging.getLogger("sms_sender")


@dataclass
class SmsMessage:
    to: str           # E.164 telefonní číslo (např. "+420775123456")
    body: str         # Plain text obsah


class SmsSender(ABC):
    @abstractmethod
    async def send(self, msg: SmsMessage) -> None:
        """Pošle SMS. Při chybě vyhodí RuntimeError."""


class MockSmsSender(SmsSender):
    """Loguje SMS místo posílání. V dev/demo režimu."""

    async def send(self, msg: SmsMessage) -> None:
        log.warning(
            "[SMS MOCK] To: %s | Body: %s",
            _redact_number(msg.to),
            msg.body,
        )


def _redact_number(num: str) -> str:
    """Pro logy — schová poslední 4 číslice (privacy v audit logech)."""
    if len(num) <= 6:
        return num
    return num[:-4] + "****"


def get_sms_sender() -> SmsSender:
    """Vrací aktivní SmsSender dle settings.sms_provider.

    - "console" / "" / "mock" → MockSmsSender (dev/demo, OTP kód = '111111')
    - "smsbrana" / "twilio"   → real provider (TODO, viz #104 follow-up)

    Pro production swap stačí přidat real implementaci a další case níže.
    """
    settings = get_settings()
    provider = (settings.sms_provider or "").strip().lower()
    if provider in ("", "console", "mock"):
        return MockSmsSender()
    # TODO: real providers (SMSbrana, Twilio) — viz #104 follow-up.
    # Před live spuštěním pro reálné zákazníky implementovat (viz memory).
    log.warning(
        "sms_provider=%s nemá real implementaci — fallback na mock", provider,
    )
    return MockSmsSender()


def is_dev_mode() -> bool:
    """Pro accountability v signature payloadu — auth_proof.is_dev_sms."""
    settings = get_settings()
    provider = (settings.sms_provider or "").strip().lower()
    return provider in ("", "console", "mock")
