"""
Model pro pracovní pozice (kategorizace prací dle NV 361/2007 Sb.).

Každá pozice je vázaná na konkrétní pracoviště (Workplace). Stejný
název pozice může existovat na více pracovištích — každá instance má
vlastní hodnocení rizikových faktorů (1:1 s RiskFactorAssessment).

Kategorie práce (1/2/2R/3/4) se odvozuje z RFA.category_proposed;
ruční override zůstává v `work_category` (zachován pro zpětnou kompat
s existujícími daty a pro případ, že OZO chce klasifikovat pozici
odlišně od měření).

Výchozí lhůty periodické prohlídky (vyhláška 79/2013 Sb. §11):
  Kategorie 1:  72 měsíců (věk < 50), 48 měsíců (věk ≥ 50)
  Kategorie 2:  48 měsíců (věk < 50), 24 měsíců (věk ≥ 50)
  Kategorie 2R: 24 měsíců
  Kategorie 3:  24 měsíců
  Kategorie 4:  12 měsíců
"""

import uuid

from sqlalchemy import Boolean, ForeignKey, SmallInteger, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin

# Výchozí lhůty periodické prohlídky v měsících dle kategorie (věk < 50).
# Tato mapa je zachována pro zpětnou kompat. Pro výpočet závislý na věku
# použij `compute_periodic_exam_months(category, age)`.
CATEGORY_DEFAULT_EXAM_MONTHS: dict[str, int] = {
    "1": 72,
    "2": 48,
    "2R": 24,
    "3": 24,
    "4": 12,
}


def compute_periodic_exam_months(category: str | None, age: int | None) -> int | None:
    """
    Výpočet lhůty periodické prohlídky podle vyhlášky 79/2013 Sb.
    a interní tabulky „Pravidla periodických lékařských prohlídek".

      Kat. 1:  dobrovolná → None (lhůta není povinně stanovena)
      Kat. 2:  věk < 50 → 48 měsíců, věk ≥ 50 → 24 měsíců
      Kat. 2R: 24 měsíců (bez rozdílu věku)
      Kat. 3:  24 měsíců (bez rozdílu věku)
      Kat. 4:  12 měsíců (bez rozdílu věku)

    Vrací None, pokud kategorie není rozpoznána nebo je 1 (dobrovolná).
    """
    if category is None:
        return None
    cat = category.strip().upper() if isinstance(category, str) else category
    if cat == "1":
        return None
    if cat == "2":
        return 24 if (age is not None and age >= 50) else 48
    if cat == "2R":
        return 24
    if cat == "3":
        return 24
    if cat == "4":
        return 12
    return None


class JobPosition(Base, TimestampMixin):
    __tablename__ = "job_positions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )

    # Pracoviště, kam pozice patří. Každá pozice je per-workplace — stejný
    # název na 2 pracovištích = 2 různé záznamy s vlastními RFA.
    workplace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workplaces.id", ondelete="RESTRICT"), nullable=False
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    # Legacy: manuální kategorie (1/2/2R/3/4). Nový model derivuje z RFA,
    # ale sloupec zachováváme pro zpětnou kompat + manuální override.
    work_category: Mapped[str | None] = mapped_column(String(3))

    # Přepsatelná lhůta periodické prohlídky
    # NULL → použij CATEGORY_DEFAULT_EXAM_MONTHS[effective_category]
    medical_exam_period_months: Mapped[int | None] = mapped_column(SmallInteger)

    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    # Opt-out vstupní prohlídky pro pozice kategorie 1 bez rizik
    # (např. čistě administrativní). Default False = vstupní se vyžaduje.
    # Pro cat 2+ se ignoruje (vstupní vždy povinná dle vyhlášky 79/2013).
    skip_vstupni_exam: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False,
    )

    created_by: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # ── Computed properties ───────────────────────────────────────────────────
    # Pozn.: RFA je nachystaná 1:1 přes job_position_id, ale relationship
    # tady záměrně NEDEFINUJEME (lazy-load v async kontextu by ho nutil být
    # selectin-loadovaný při každém selectu). Derived hodnoty dopočítáváme
    # ve service/API vrstvě, která má k dispozici async session.

    @property
    def effective_exam_period_months(self) -> int | None:
        """
        Efektivní lhůta periodické prohlídky.
        Priorita: ruční override > výchozí z kategorie (pokud zadaná) > None.
        """
        if self.medical_exam_period_months is not None:
            return self.medical_exam_period_months
        if self.work_category is not None:
            return CATEGORY_DEFAULT_EXAM_MONTHS.get(self.work_category)
        return None
