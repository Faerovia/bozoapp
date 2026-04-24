import uuid
from datetime import UTC, date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

DUE_SOON_DAYS = 30

# Striktní enum typů zařízení (česky slug, labely řeší frontend).
DEVICE_TYPES = (
    "elektro",          # elektrické rozvody / zařízení (vyhl. 50/1978, NV 194/2022)
    "hromosvody",       # hromosvody a ochrana před bleskem (ČSN EN 62305)
    "plyn",             # plynová zařízení (vyhl. 21/1979)
    "kotle",            # kotle a topné zdroje
    "tlakove_nadoby",   # tlakové nádoby (NV 26/2003)
    "vytahy",           # výtahy (NV 378/2001)
    "spalinove_cesty",  # spalinové cesty (vyhl. 34/2016)
)


class Revision(Base, TimestampMixin):
    """
    Záznam o vyhrazeném zařízení (= „revize" v UI).

    Samotné provedené kontroly jsou evidovány v `revision_records`
    (timeline, 1:N vůči Revision).
    """

    __tablename__ = "revisions"
    __table_args__ = (
        CheckConstraint("valid_months > 0", name="ck_revisions_valid_months"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # ── Identifikace zařízení ──────────────────────────────────────────────
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Legacy free-text — v novém modelu se primárně používá plant_id.
    # Ponecháváme pro popis upřesňující umístění (např. patro, místnost).
    location: Mapped[str | None] = mapped_column(String(255))

    # Provozovna — povinná v novém modelu (migrace nechává nullable pro
    # backfill; nové záznamy service validuje jako required).
    plant_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("plants.id", ondelete="RESTRICT"), nullable=True
    )
    # Interní ID / výrobní štítek
    device_code: Mapped[str | None] = mapped_column(String(100))
    # Striktní enum 7 hodnot (viz DEVICE_TYPES)
    device_type: Mapped[str | None] = mapped_column(String(30))
    # Legacy volný typ (elektrická/gas/…) — použijeme pro backfill. Nové
    # záznamy ukládají do device_type.
    revision_type: Mapped[str] = mapped_column(String(50), default="other", nullable=False)

    # ── Termín revize ──────────────────────────────────────────────────────
    # Derived z latest revision_record.performed_at; ukládáme kopii pro
    # rychlé řazení / filtering bez JOINu.
    last_revised_at: Mapped[date | None] = mapped_column(Date)
    valid_months: Mapped[int | None] = mapped_column(SmallInteger)
    next_revision_at: Mapped[date | None] = mapped_column(Date)

    # ── Kontakt na revizního technika ───────────────────────────────────────
    # Legacy sloupec contractor = jméno/firma; nové sloupce rozdělují kontakt.
    contractor: Mapped[str | None] = mapped_column(String(255))
    technician_name: Mapped[str | None] = mapped_column(String(255))
    technician_email: Mapped[str | None] = mapped_column(String(255))
    technician_phone: Mapped[str | None] = mapped_column(String(50))

    # ── Zodpovědný uživatel (legacy; nový model to řeší přes
    #     employee_plant_responsibilities M:N na úrovni provozovny) ────────
    responsible_user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL")
    )

    # ── QR polep ──────────────────────────────────────────────────────────
    qr_token: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    @property
    def due_status(self) -> str:
        """
        - 'no_schedule'  – next_revision_at není zadán
        - 'ok'           – termín je dál než DUE_SOON_DAYS
        - 'due_soon'     – termín je do DUE_SOON_DAYS
        - 'overdue'      – termín je v minulosti
        """
        if self.next_revision_at is None:
            return "no_schedule"
        today = datetime.now(UTC).date()
        delta = (self.next_revision_at - today).days
        if delta < 0:
            return "overdue"
        if delta <= DUE_SOON_DAYS:
            return "due_soon"
        return "ok"


class RevisionRecord(Base):
    """Jeden provedený záznam revize (= historie kontrol)."""

    __tablename__ = "revision_records"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    revision_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("revisions.id", ondelete="CASCADE"), nullable=False
    )

    performed_at: Mapped[date] = mapped_column(Date, nullable=False)
    pdf_path: Mapped[str | None] = mapped_column(String(500))
    image_path: Mapped[str | None] = mapped_column(String(500))

    technician_name: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )


class EmployeePlantResponsibility(Base):
    """
    M:N mapování: zaměstnanec × provozovna, za kterou je zodpovědný.
    Zaměstnanec s alespoň jedním řádkem = is_equipment_responsible.
    Dostává notifikace o revizích blížících se expiraci v dané provozovně
    a smí zaznamenat revizi u zařízení v dané provozovně.
    """

    __tablename__ = "employee_plant_responsibilities"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id", ondelete="CASCADE"), nullable=False
    )
    plant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
