"""
Modely pro OOPP modul (NV 390/2021 Sb. — Příloha č. 2).

Hierarchie:
  JobPosition
    ├── PositionRiskGrid    (1:1) — matrix 14 bodyparts × 26 typů rizik
    ├── PositionOoppItem    (N)   — co je nutné vydávat (per body_part)
    │     └── EmployeeOoppIssue   — vydávací událost (last/next dates)
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

OOPP_EXPIRING_SOON_DAYS = 30


# ── Konstanty pro Přílohu č. 2 NV 390/2021 ──────────────────────────────────

# Body parts — 14 řádků tabulky (NV 390/2021 Sb., Příloha č. 2)
# (key, label, group)
BODY_PARTS: list[tuple[str, str, str | None]] = [
    ("A", "lebka", "hlava"),
    ("B", "celá hlava", "hlava"),
    ("C", "uši / sluch", None),
    ("D", "oči / zrak", None),
    ("E", "obličej", None),
    ("F", "dýchací orgány", None),
    ("G", "ruce", None),
    ("H", "paže (části)", None),
    ("I", "nohy (chodidla)", None),
    ("J", "nohy (části)", None),
    ("K", "pokožka", None),
    ("L", "trup/břicho", None),
    ("M", "část těla", None),
    ("N", "celé tělo", None),
]

# Risk columns — 26 sloupců (1-26) tabulky.
# (col_num, label, subgroup, group)
RISK_COLUMNS: list[tuple[int, str, str | None, str]] = [
    (1,  "náraz",                                                 "mechanická",      "fyzikální"),
    (2,  "uklouznutí",                                            "mechanická",      "fyzikální"),
    (3,  "pády z výšky",                                          "mechanická",      "fyzikální"),
    (4,  "vibrace",                                               "mechanická",      "fyzikální"),
    (5,  "statické stlačení části těla",                          "mechanická",      "fyzikální"),
    (6,  "odření, perforace, řezné a jiné rány, kousnutí, bodnutí", "mechanická",    "fyzikální"),
    (7,  "zachycení, uskřípnutí",                                 "mechanická",      "fyzikální"),
    (8,  "hluk",                                                  None,              "fyzikální"),
    (9,  "teplo, oheň",                                           "tepelná",         "fyzikální"),
    (10, "chlad",                                                 "tepelná",         "fyzikální"),
    (11, "úraz elektrickým proudem",                              "elektrická",      "fyzikální"),
    (12, "statická elektřina",                                    "elektrická",      "fyzikální"),
    (13, "neionizující záření",                                   "radiační",        "fyzikální"),
    (14, "ionizující záření",                                     "radiační",        "fyzikální"),
    (15, "prach, vlákna, dýmy, výpary",                           "aerosoly pevné",  "chemická"),
    (16, "mlhy, jemné mlhy",                                      "aerosoly kapalné", "chemická"),
    (17, "ponoření",                                              "kapaliny",        "chemická"),
    (18, "postříkání, rozprášení, vystříknutí",                   "kapaliny",        "chemická"),
    (19, "plyny, páry",                                           None,              "chemická"),
    (20, "pevných a kapalných (aerosoly)",                        "aerosoly",        "biologické"),
    (21, "přímý a nepřímý kontakt (kapaliny)",                    "kapaliny",        "biologické"),
    (22, "postříkání, rozprášení, vystříknutí (kapaliny)",        "kapaliny",        "biologické"),
    (23, "přímý a nepřímý kontakt (materiály, osoby, zvířata)",   "materiály",       "biologické"),
    (24, "utonutí",                                               None,              "jiná"),
    (25, "nedostatek kyslíku",                                    None,              "jiná"),
    (26, "nedostatečná viditelnost",                              None,              "jiná"),
]

VALID_BODY_PARTS = frozenset(bp[0] for bp in BODY_PARTS)
VALID_RISK_COLS = frozenset(rc[0] for rc in RISK_COLUMNS)

# Label lookup pro generátory dokumentů — sjednocený slovník
# RA / Účaz / OOPP odkazují na tyto popisy.
BODY_PART_LABELS: dict[str, str] = {bp[0]: bp[1] for bp in BODY_PARTS}
OOPP_RISK_COLUMN_LABELS: dict[int, str] = {rc[0]: rc[1] for rc in RISK_COLUMNS}


# ── Modely ──────────────────────────────────────────────────────────────────


class PositionRiskGrid(Base, TimestampMixin):
    """
    Vyhodnocení rizik OOPP per pracovní pozice (NV 390/2021 Sb., Příloha č. 2).

    `grid` je JSONB struktura ve tvaru:
        {"<body_part>": [<risk_col>, <risk_col>, ...], ...}
    Např. {"G": [1, 6], "I": [3]} = ruce mají rizika náraz+odření,
    nohy chodidla mají riziko pád z výšky.
    """

    __tablename__ = "position_risk_grids"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    job_position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_positions.id", ondelete="CASCADE"),
        nullable=False, unique=True,
    )

    grid: Mapped[dict[str, list[int]]] = mapped_column(
        JSONB, nullable=False, default=dict,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    @property
    def has_any_risk(self) -> bool:
        """True pokud je alespoň jedna buňka zaškrtnutá."""
        return any(cols for cols in self.grid.values())


class PositionOoppItem(Base, TimestampMixin):
    """OOPP přidělené pracovní pozici (per body part). Výchozí katalog."""

    __tablename__ = "position_oopp_items"
    __table_args__ = (
        CheckConstraint(
            "body_part IN ('A','B','C','D','E','F','G','H','I','J','K','L','M','N')",
            name="ck_poi_body_part",
        ),
        CheckConstraint(
            "valid_months IS NULL OR valid_months > 0",
            name="ck_poi_valid_months",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    job_position_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("job_positions.id", ondelete="CASCADE"), nullable=False
    )

    body_part: Mapped[str] = mapped_column(String(2), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    valid_months: Mapped[int | None] = mapped_column(SmallInteger)

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class EmployeeOoppIssue(Base, TimestampMixin):
    """Záznam výdeje OOPP zaměstnanci. Last/next dates pro evidenci."""

    __tablename__ = "employee_oopp_issues"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'returned', 'discarded')",
            name="ck_eoi_status",
        ),
        CheckConstraint("quantity > 0", name="ck_eoi_quantity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    position_oopp_item_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("position_oopp_items.id", ondelete="CASCADE"), nullable=False
    )

    issued_at: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date)

    quantity: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    size_spec: Mapped[str | None] = mapped_column(String(50))
    serial_number: Mapped[str | None] = mapped_column(String(100))

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Univerzální digitální podpis (migrace 057). Pokud je nastaven, výdej
    # byl zaměstnancem potvrzen přes /signatures/verify (heslo nebo SMS OTP).
    signature_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("signatures.id", ondelete="SET NULL")
    )

    # Pozn.: TimestampMixin už dodává created_at/updated_at TIMESTAMPTZ.
    # Tady redefinujeme jen pro kompatibilitu s dříve používaným vzorem
    # (dovolíme dát explicit TZ-aware default, byť mixin to umí).

    @property
    def validity_status(self) -> str:
        """no_expiry / valid / expiring_soon / expired — pro UI badge."""
        if self.valid_until is None:
            return "no_expiry"
        today = datetime.now(UTC).date()
        delta = (self.valid_until - today).days
        if delta < 0:
            return "expired"
        if delta <= OOPP_EXPIRING_SOON_DAYS:
            return "expiring_soon"
        return "valid"


# Pozn.: stará třída OOPPAssignment + tabulka oopp_assignments byly v
# migraci 025 odstraněny. Žádný backward-compat alias nepotřebujeme,
# protože services/api už ji neimportují (kontrola v ruff/mypy).
