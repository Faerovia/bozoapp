"""
Model pro hodnocení rizikových faktorů (seznam rizikových faktorů pracovního prostředí).

Každý záznam = jeden řádek dokumentu "Seznam rizikových faktorů"
= kombinace (pracoviště + profese) s hodnoceními 13 faktorů dle NV 361/2007.

Hodnocení: '1' | '2' | '2R' | '3' | '4' | None
Celková kategorie = MAX numericky (2R = 2.5 pro porovnání, zobrazuje se jako '2R').
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# Pořadí faktorů dle NV 361/2007 (používá se pro export a display)
RF_FIELDS = [
    "rf_prach",
    "rf_chem",
    "rf_hluk",
    "rf_vibrace",
    "rf_zareni",
    "rf_tlak",
    "rf_fyz_zatez",
    "rf_prac_poloha",
    "rf_teplo",
    "rf_chlad",
    "rf_psych",
    "rf_zrak",
    "rf_bio",
]

RF_LABELS = {
    "rf_prach":       "Prach",
    "rf_chem":        "Chemické látky",
    "rf_hluk":        "Hluk",
    "rf_vibrace":     "Vibrace",
    "rf_zareni":      "Neionizující záření a EM pole",
    "rf_tlak":        "Práce ve zvýšeném tlaku vzduchu",
    "rf_fyz_zatez":   "Fyzická zátěž",
    "rf_prac_poloha": "Pracovní poloha",
    "rf_teplo":       "Zátěž teplem",
    "rf_chlad":       "Zátěž chladem",
    "rf_psych":       "Psychická zátěž",
    "rf_zrak":        "Zraková zátěž",
    "rf_bio":         "Práce s biologickými činiteli",
}

VALID_RATINGS = frozenset({"1", "2", "2R", "3", "4"})


def _rating_numeric(val: str | None) -> float:
    """Pro porovnání: 2R = 2.5, ostatní jsou celá čísla."""
    if val is None:
        return 0.0
    if val == "2R":
        return 2.5
    try:
        return float(val)
    except ValueError:
        return 0.0


class RiskFactorAssessment(Base, TimestampMixin):
    __tablename__ = "risk_factor_assessments"
    __table_args__ = (
        CheckConstraint(
            "rf_prach IN ('1','2','2R','3','4') OR rf_prach IS NULL",
            name="ck_rfa_ratings",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    workplace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workplaces.id", ondelete="CASCADE"), nullable=False
    )

    profese: Mapped[str] = mapped_column(String(255), nullable=False)
    operator_names: Mapped[str | None] = mapped_column(Text)

    worker_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)
    women_count: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    # 13 rizikových faktorů
    rf_prach:       Mapped[str | None] = mapped_column(String(3))
    rf_chem:        Mapped[str | None] = mapped_column(String(3))
    rf_hluk:        Mapped[str | None] = mapped_column(String(3))
    rf_vibrace:     Mapped[str | None] = mapped_column(String(3))
    rf_zareni:      Mapped[str | None] = mapped_column(String(3))
    rf_tlak:        Mapped[str | None] = mapped_column(String(3))
    rf_fyz_zatez:   Mapped[str | None] = mapped_column(String(3))
    rf_prac_poloha: Mapped[str | None] = mapped_column(String(3))
    rf_teplo:       Mapped[str | None] = mapped_column(String(3))
    rf_chlad:       Mapped[str | None] = mapped_column(String(3))
    rf_psych:       Mapped[str | None] = mapped_column(String(3))
    rf_zrak:        Mapped[str | None] = mapped_column(String(3))
    rf_bio:         Mapped[str | None] = mapped_column(String(3))

    category_override: Mapped[str | None] = mapped_column(String(3))
    sort_order: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # ── Computed properties ───────────────────────────────────────────────────

    @property
    def category_proposed(self) -> str:
        """
        Navržená celková kategorie = MAX ze všech faktorů.
        category_override má přednost pokud je nastaven.
        2R se zobrazí pokud je nejvyšší hodnocení 2R (jinak celé číslo).
        """
        if self.category_override:
            return self.category_override

        ratings = [getattr(self, f) for f in RF_FIELDS]
        non_null = [r for r in ratings if r is not None]
        if not non_null:
            return "1"

        max_numeric = max(_rating_numeric(r) for r in non_null)

        # 2R = 2.5 numericky → zobrazíme jako '2R'
        if max_numeric == 2.5:
            return "2R"
        return str(int(max_numeric))

    @property
    def ratings_dict(self) -> dict[str, str | None]:
        """Slovník {field: value} pro všech 13 faktorů."""
        return {f: getattr(self, f) for f in RF_FIELDS}
