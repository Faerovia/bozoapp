"""
Testy pro týdenní notifikační task.

Plný end-to-end test s e-mailem vyžaduje SMTP fixture — ten nemáme.
Testujeme proto čistě:
- _format_due: výstupy pro záporné / 0 / 1 / N dní
- _build_email_body: správné složení subject + body pro daný vstup
"""
from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

from app.tasks.weekly_revision_notifications import _build_email_body, _format_due


def test_format_due_overdue() -> None:
    assert _format_due(-5) == "PO TERMÍNU o 5 dní"


def test_format_due_today() -> None:
    assert _format_due(0) == "dnes"


def test_format_due_tomorrow() -> None:
    assert _format_due(1) == "zítra"


def test_format_due_future() -> None:
    assert _format_due(14) == "za 14 dní"


def test_build_email_body_format() -> None:
    employee = SimpleNamespace(
        first_name="Jan",
        last_name="Novák",
        email="jan@firma.cz",
    )
    rev_a = SimpleNamespace(
        id=uuid.uuid4(),
        title="Elektrorozvaděč R1",
        device_code="RZV-001",
        next_revision_at=date(2026, 5, 10),
    )
    rev_b = SimpleNamespace(
        id=uuid.uuid4(),
        title="Kotel K1",
        device_code=None,
        next_revision_at=date(2026, 5, 1),
    )
    subject, body = _build_email_body(
        employee,  # type: ignore[arg-type]
        "Provozovna Praha",
        [(rev_a, 16), (rev_b, 7)],
    )

    assert "Provozovna Praha" in subject
    assert "(2)" in subject

    # Body obsahuje jméno
    assert "Jan Novák" in body
    # Seřazeno podle next_revision_at: kotel (2026-05-01) nejdřív
    kotel_idx = body.index("Kotel K1")
    elektro_idx = body.index("Elektrorozvaděč R1")
    assert kotel_idx < elektro_idx

    # Device code v závorce
    assert "(RZV-001)" in body
    # Formát due
    assert "za 7 dní" in body
    assert "za 16 dní" in body


def test_build_email_body_overdue_label() -> None:
    employee = SimpleNamespace(
        first_name="Eva",
        last_name="Dvořáková",
        email="eva@firma.cz",
    )
    rev = SimpleNamespace(
        id=uuid.uuid4(),
        title="Výtah V1",
        device_code=None,
        next_revision_at=date(2025, 1, 1),
    )
    subject, body = _build_email_body(
        employee,  # type: ignore[arg-type]
        "Sklad",
        [(rev, -15)],
    )
    assert "PO TERMÍNU o 15 dní" in body
    assert "Výtah V1" in body
