"""Modul Provozní deníky — strojní zařízení s denními/týdenními zápisy."""
import secrets
import uuid
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# 3-way způsobilost zařízení k provozu
CAPABILITY_VALUES = ("yes", "no", "conditional")


def _gen_qr_token() -> str:
    return secrets.token_urlsafe(48)[:64]

# Kategorie strojního zařízení s doporučenou periodicitou (NV 378/2001 Sb. atd.)
DEVICE_CATEGORIES = (
    "vzv",                # Vysokozdvižné vozíky (denně před směnou)
    "kotelna",            # Kotelny (denně dle obsluhy)
    "tlakova_nadoba",     # Tlakové nádoby TNS
    "jerab",              # Jeřáby a zdvihadla
    "eps",                # Elektrická požární signalizace
    "sprinklery",         # Stabilní hasicí zařízení
    "cov",                # Čističky odpadních vod / odlučovače
    "diesel",             # Náhradní zdroje (dieselagregáty)
    "regaly_sklad",       # Regálové systémy ve skladech
    "vytah",              # Výtahy osobní/nákladní
    "stroje_riziko",      # Stroje s vyšším rizikem (lisy, pily)
    "other",              # Jiné
)

PERIOD_VALUES = ("daily", "weekly", "monthly", "shift", "other")


class OperatingLogDevice(Base, TimestampMixin):
    __tablename__ = "operating_log_devices"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'archived')", name="ck_oplog_status"),
        CheckConstraint(
            "period IN ('daily', 'weekly', 'monthly', 'shift', 'other')",
            name="ck_oplog_period",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    category: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    device_code: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(255))
    plant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plants.id", ondelete="SET NULL")
    )
    workplace_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("workplaces.id", ondelete="SET NULL")
    )

    # Pole kontrolních úkonů — list[str], 1-20 položek.
    check_items: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    period: Mapped[str] = mapped_column(String(20), default="daily", nullable=False)
    period_note: Mapped[str | None] = mapped_column(String(255))

    # QR token — odkazuje na /devices/{qr_token}/operating-log (zápis na místě)
    qr_token: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, default=_gen_qr_token,
    )

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # Zodpovědný zaměstnanec — chodí mu no-entry alert (cron). Migrace 056.
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id", ondelete="SET NULL")
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )


class OperatingLogEntry(Base):
    __tablename__ = "operating_log_entries"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    device_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("operating_log_devices.id", ondelete="CASCADE"), nullable=False
    )

    performed_at: Mapped[date] = mapped_column(Date, nullable=False)
    performed_by_name: Mapped[str] = mapped_column(String(255), nullable=False)
    # Pole stringů paralelní s OperatingLogDevice.check_items.
    # Hodnoty per úkon: 'yes' | 'no' | 'conditional'
    capable_items: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list,
    )
    # Souhrnný stav: 'yes' | 'no' | 'conditional'
    overall_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="yes",
    )
    notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC),
    )
