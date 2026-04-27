"""SMS gateway abstrakce.

Provider se řídí přes settings.sms_provider:
- "" / "mock" / "console" → MockSmsSender (loguje do warnings, neposílá)
- "smsbrana"              → SmsBranaSender (cz provider, ~0.45 Kč/SMS)

Pro budoucí providery (Twilio, Vonage, AWS SNS) stačí přidat třídu
podle interface SmsSender a routing v get_sms_sender().

V dev/mock módu OTP kód generuje signatures service vždy jako '111111'
— sender o tom neví, dostává plain text který má poslat.

Pro reálné zákazníky se před live release přepne na placený TSA
+ skutečnou SMS gateway (viz memory project_signature_architecture).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

import httpx

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


class SmsBranaSender(SmsSender):
    """SMSbrána.cz HTTP provider.

    Doc: https://www.smsbrana.cz/dokumenty/SMSconnect_dokumentace.pdf
    Endpoint: GET https://api.smsbrana.cz/smsconnect/http.php
    Parametry: action=send_sms, login, password, number, message
    Cena: ~0.45-0.70 Kč/SMS, free trial ~30 SMS pro nové účty.

    Volitelně lze místo `password` použít MD5(password+sul+time) hash
    s parametrem `auth`, ale plain login/password přes HTTPS je
    pro demo dostatečné.

    Číslo musí být v mezinárodním formátu BEZ '+' (např. "420775123456").
    """

    URL = "https://api.smsbrana.cz/smsconnect/http.php"

    def __init__(self, login: str, password: str) -> None:
        if not login or not password:
            raise ValueError("SmsBrana vyžaduje login + password")
        self.login = login
        self.password = password

    async def send(self, msg: SmsMessage) -> None:
        # SMSbrána očekává číslo bez '+' prefixu
        number = msg.to.lstrip("+")
        params = {
            "action": "send_sms",
            "login": self.login,
            "password": self.password,
            "number": number,
            "message": msg.body,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(self.URL, params=params)
        except httpx.HTTPError as e:
            log.exception("SmsBrana request failed")
            raise RuntimeError(f"SMSbrana network error: {e}") from e

        if resp.status_code != 200:
            raise RuntimeError(
                f"SMSbrana HTTP {resp.status_code}: {resp.text[:200]}",
            )

        # Response je XML s <err>0</err> při úspěchu, jinak chybový kód.
        # Pro jednoduchost stačí kontrola, že '<err>0</err>' je v textu.
        body = resp.text
        if "<err>0</err>" in body:
            log.info("SmsBrana sent OK to %s", _redact_number(msg.to))
            return
        log.error(
            "SmsBrana failed to %s: response=%s",
            _redact_number(msg.to), body[:300],
        )
        raise RuntimeError(f"SMSbrana send failed: {body[:200]}")


def _redact_number(num: str) -> str:
    """Pro logy — schová poslední 4 číslice (privacy v audit logech)."""
    if len(num) <= 6:
        return num
    return num[:-4] + "****"


def get_sms_sender() -> SmsSender:
    """Vrací aktivní SmsSender dle settings.sms_provider.

    Routing:
    - "" / "mock" / "console"  → MockSmsSender (loguje, neposílá)
    - "smsbrana"               → SmsBranaSender (vyžaduje login+password)

    Pokud sms_provider='smsbrana' ale credentials chybí, fallbackneme
    na MockSmsSender (s warning log) — žádný crash při deploy.
    """
    settings = get_settings()
    provider = (settings.sms_provider or "").strip().lower()

    if provider in ("", "console", "mock"):
        return MockSmsSender()

    if provider == "smsbrana":
        login = (getattr(settings, "sms_login", "") or "").strip()
        password = (getattr(settings, "sms_password", "") or "").strip()
        if not login or not password:
            log.warning(
                "sms_provider=smsbrana ale chybí SMS_LOGIN/SMS_PASSWORD — "
                "fallback na mock",
            )
            return MockSmsSender()
        return SmsBranaSender(login=login, password=password)

    log.warning(
        "sms_provider=%s není implementováno — fallback na mock", provider,
    )
    return MockSmsSender()


def is_dev_mode() -> bool:
    """Pro accountability v signature payloadu — auth_proof.is_dev_sms.

    True pokud aktivní sender je MockSmsSender (žádný real provider).
    Tím signatures service ví, že má vygenerovat OTP '111111'
    místo náhodného kódu.
    """
    settings = get_settings()
    provider = (settings.sms_provider or "").strip().lower()
    if provider in ("", "console", "mock"):
        return True
    if provider == "smsbrana":
        login = (getattr(settings, "sms_login", "") or "").strip()
        password = (getattr(settings, "sms_password", "") or "").strip()
        return not (login and password)
    return True  # neznámý provider → dev mode
