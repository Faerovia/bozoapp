import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.validation import assert_in_tenant
from app.models.employee import Employee
from app.models.job_position import JobPosition, compute_periodic_exam_months
from app.models.medical_exam import MedicalExam
from app.models.risk_factor_assessment import RF_FIELDS, RiskFactorAssessment
from app.schemas.medical_exams import (
    MedicalExamCreateRequest,
    MedicalExamUpdateRequest,
)
from app.services.medical_specialty_catalog import (
    SPECIALTY_CATALOG,
    get_periodicity_for_category,
    get_required_specialties_for_factors,
)
from app.services.platform_settings import get_setting

DEFAULT_AUTO_CHECK_THROTTLE_MINUTES = 30


async def _throttle_minutes(db: AsyncSession) -> int:
    """Načte hodnotu throttlu z platform_settings (s fallback na default)."""
    val = await get_setting(
        db, "medical_exam.auto_check_throttle_minutes",
        DEFAULT_AUTO_CHECK_THROTTLE_MINUTES,
    )
    try:
        return int(val)
    except (TypeError, ValueError):
        return DEFAULT_AUTO_CHECK_THROTTLE_MINUTES


# Backward compat — pro testy a callsites mimo tento modul
AUTO_CHECK_THROTTLE_MINUTES = DEFAULT_AUTO_CHECK_THROTTLE_MINUTES


def _age_at(reference: date, birth_date: date | None) -> int | None:
    """Spočítá věk v celých letech k referenčnímu datu."""
    if birth_date is None:
        return None
    age = reference.year - birth_date.year
    # Korekce pokud ještě nebylo letošní výročí
    if (reference.month, reference.day) < (birth_date.month, birth_date.day):
        age -= 1
    return age


async def _resolve_periodic_months(
    db: AsyncSession,
    *,
    employee_id: uuid.UUID,
    job_position_id: uuid.UUID | None,
    exam_date: date,
    tenant_id: uuid.UUID,
) -> int | None:
    """
    Auto-výpočet lhůty periodické prohlídky podle (kategorie z RFA, věk).
    Pravidla čte z platform_settings.medical_exam.periodicity_months
    s fallback na hardcoded vyhlášku 79/2013 Sb.
    """
    # Věk zaměstnance
    emp = (await db.execute(
        select(Employee).where(
            Employee.id == employee_id,
            Employee.tenant_id == tenant_id,
        )
    )).scalar_one_or_none()
    age = _age_at(exam_date, emp.birth_date) if emp else None

    # Kategorie z RFA pozice (preferuje category_proposed, fallback work_category)
    category: str | None = None
    if job_position_id is not None:
        pos = (await db.execute(
            select(JobPosition).where(JobPosition.id == job_position_id)
        )).scalar_one_or_none()
        if pos is not None:
            category = pos.work_category
        rfa = (await db.execute(
            select(RiskFactorAssessment).where(
                RiskFactorAssessment.job_position_id == job_position_id,
                RiskFactorAssessment.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if rfa is not None and rfa.category_proposed:
            category = rfa.category_proposed

    # Načti pravidla z platform_settings
    rules = await get_setting(db, "medical_exam.periodicity_months", None)
    if rules and category and isinstance(rules, dict):
        cat_rule = rules.get(category)
        if isinstance(cat_rule, dict):
            key = "over_50" if (age is not None and age >= 50) else "under_50"
            months = cat_rule.get(key)
            if months is not None:
                try:
                    return int(months)
                except (TypeError, ValueError):
                    pass
            # Pokud má pravidlo „null" → dobrovolná prohlídka
            if key in cat_rule and cat_rule[key] is None:
                return None

    # Fallback: hardcoded hodnoty z modelu (vyhláška 79/2013 Sb.)
    return compute_periodic_exam_months(category, age)


def _specialty_label(specialty: str | None) -> str | None:
    if not specialty:
        return None
    for entry in SPECIALTY_CATALOG:
        if entry["key"] == specialty:
            return entry["label"]
    return specialty  # fallback — neznámé


async def attach_employee_info(
    db: AsyncSession,
    exams: list[MedicalExam],
    *,
    include_personal_id: bool = False,
) -> list[dict[str, Any]]:
    """
    Obohatí prohlídky o jméno + RČ zaměstnance + název pozice.
    Vrací list dictů kompatibilních s MedicalExamResponse.

    Pozn.: čerstvě flushnuté ORM objekty mohou mít expired atributy v async
    session — proto čteme přes db.refresh, ne přes __table__.columns + getattr.
    """
    if not exams:
        return []

    # Refresh každé prohlídky, aby všechna pole byla načtená v tomto greenlet
    for exam in exams:
        await db.refresh(exam)

    employee_ids = {e.employee_id for e in exams}
    position_ids = {e.job_position_id for e in exams if e.job_position_id}

    emp_rows = (await db.execute(
        select(Employee).where(Employee.id.in_(employee_ids))
    )).scalars().all()
    emp_map = {emp.id: emp for emp in emp_rows}

    pos_map: dict[uuid.UUID, JobPosition] = {}
    if position_ids:
        pos_rows = (await db.execute(
            select(JobPosition).where(JobPosition.id.in_(position_ids))
        )).scalars().all()
        pos_map = {p.id: p for p in pos_rows}

    result: list[dict[str, Any]] = []
    for exam in exams:
        emp = emp_map.get(exam.employee_id)
        pos = pos_map.get(exam.job_position_id) if exam.job_position_id else None
        d: dict[str, Any] = {
            "id":                 exam.id,
            "tenant_id":          exam.tenant_id,
            "employee_id":        exam.employee_id,
            "job_position_id":    exam.job_position_id,
            "exam_category":      exam.exam_category,
            "exam_type":          exam.exam_type,
            "specialty":          exam.specialty,
            "exam_date":          exam.exam_date,
            "result":             exam.result,
            "physician_name":     exam.physician_name,
            "valid_months":       exam.valid_months,
            "valid_until":        exam.valid_until,
            "report_path":        exam.report_path,
            "notes":              exam.notes,
            "status":             exam.status,
            "created_by":         exam.created_by,
            "validity_status":    exam.validity_status,
            "days_until_expiry":  exam.days_until_expiry,
            "employee_name": (
                f"{emp.first_name} {emp.last_name}".strip() if emp else None
            ),
            "employee_personal_id": (
                emp.personal_id if (emp and include_personal_id) else None
            ),
            "job_position_name": pos.name if pos else None,
            "work_category":     pos.work_category if pos else None,
            "specialty_label":   _specialty_label(exam.specialty),
            "has_report":        bool(exam.report_path),
        }
        result.append(d)
    return result


async def get_medical_exams(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    *,
    employee_id: uuid.UUID | None = None,
    exam_type: str | None = None,
    status: str | None = None,
    validity_status: str | None = None,
) -> list[MedicalExam]:
    query = (
        select(MedicalExam)
        .where(MedicalExam.tenant_id == tenant_id)
        .order_by(MedicalExam.exam_date.desc())
    )
    if employee_id is not None:
        query = query.where(MedicalExam.employee_id == employee_id)
    if exam_type is not None:
        query = query.where(MedicalExam.exam_type == exam_type)
    if status is not None:
        query = query.where(MedicalExam.status == status)

    result = await db.execute(query)
    rows = list(result.scalars().all())

    # validity_status je computed property – filtrujeme v Pythonu
    if validity_status is not None:
        rows = [r for r in rows if r.validity_status == validity_status]

    return rows


async def get_medical_exam_by_id(
    db: AsyncSession, exam_id: uuid.UUID, tenant_id: uuid.UUID
) -> MedicalExam | None:
    result = await db.execute(
        select(MedicalExam).where(
            MedicalExam.id == exam_id,
            MedicalExam.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_medical_exam(
    db: AsyncSession,
    data: MedicalExamCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> MedicalExam:
    await assert_in_tenant(db, Employee, data.employee_id, tenant_id, field_name="employee_id")
    if data.job_position_id is not None:
        await assert_in_tenant(
            db, JobPosition, data.job_position_id, tenant_id, field_name="job_position_id"
        )

    valid_months = data.valid_months
    valid_until = data.valid_until
    # Auto-výpočet lhůty pro periodickou prohlídku — jen pokud OZO zadal exam_date
    # (pokud chybí, prohlídka neproběhla → necháme valid_until=None → expired)
    if (
        data.exam_type == "periodicka"
        and valid_months is None
        and valid_until is None
        and data.exam_date is not None
    ):
        valid_months = await _resolve_periodic_months(
            db,
            employee_id=data.employee_id,
            job_position_id=data.job_position_id,
            exam_date=data.exam_date,
            tenant_id=tenant_id,
        )
        if valid_months is not None:
            import calendar
            d = data.exam_date
            month = d.month + valid_months
            year = d.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            valid_until = date(year, month, min(d.day, last_day))

    exam = MedicalExam(
        tenant_id=tenant_id,
        created_by=created_by,
        employee_id=data.employee_id,
        job_position_id=data.job_position_id,
        exam_category=data.exam_category,
        exam_type=data.exam_type,
        specialty=data.specialty,
        exam_date=data.exam_date,
        result=data.result,
        physician_name=data.physician_name,
        valid_months=valid_months,
        valid_until=valid_until,
        notes=data.notes,
    )
    db.add(exam)
    await db.flush()
    return exam


async def generate_initial_exam_requests(
    db: AsyncSession,
    employee_id: uuid.UUID,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> dict[str, Any]:
    """
    Auto-vygeneruje vstupní lékařskou prohlídku + povinné odborné prohlídky
    podle KONKRÉTNÍCH rizikových faktorů na pozici zaměstnance (z RFA).

    Klíčový princip: odborná prohlídka se přidělí JEN podle daného faktoru,
    ne podle souhrnné kategorie. Příklad: pozice má rf_hluk=4 ale ostatní 1
    → přiřadí se POUZE audiometrie (1× za rok), žádná spirometrie/RTG/EKG.

    Periodicita každé odborné prohlídky se odvozuje z ratingu faktoru,
    který ji vyvolal (ne z max kategorie pozice).

    Záznamy se vytvoří jako draft (bez výsledku) — OZO doplní po skutečné
    prohlídce. Existující aktivní záznam stejného typu/specialty se přeskočí.
    """
    await assert_in_tenant(db, Employee, employee_id, tenant_id, field_name="employee_id")
    emp = (await db.execute(
        select(Employee).where(Employee.id == employee_id)
    )).scalar_one()

    job_position_id: uuid.UUID | None = emp.job_position_id
    work_category: str | None = None
    factor_ratings: dict[str, str | None] = {}
    pos: JobPosition | None = None

    if job_position_id is not None:
        pos = (await db.execute(
            select(JobPosition).where(JobPosition.id == job_position_id)
        )).scalar_one_or_none()
        if pos is not None:
            work_category = pos.work_category

        # Načti RFA pro pozici (může neexistovat)
        rfa = (await db.execute(
            select(RiskFactorAssessment).where(
                RiskFactorAssessment.job_position_id == job_position_id,
                RiskFactorAssessment.tenant_id == tenant_id,
            )
        )).scalar_one_or_none()
        if rfa is not None:
            factor_ratings = {f: getattr(rfa, f, None) for f in RF_FIELDS}

    # Existující aktivní prohlídky tohoto zaměstnance
    existing = (await db.execute(
        select(MedicalExam).where(
            MedicalExam.employee_id == employee_id,
            MedicalExam.tenant_id == tenant_id,
            MedicalExam.status == "active",
        )
    )).scalars().all()
    existing_specialties = {e.specialty for e in existing if e.specialty}
    has_vstupni = any(
        e.exam_type == "vstupni" and e.validity_status != "expired" for e in existing
    )

    created_exams: list[MedicalExam] = []
    skipped: list[str] = []

    # 1) Vstupní preventivní prohlídka.
    # Default: vždy (vyhláška 79/2013). Výjimka: pozice cat 1 s flagem
    # `skip_vstupni_exam=True` (OZO/HR opt-out pro pozice bez rizik).
    skip_vstupni = False
    if pos is not None and getattr(pos, "skip_vstupni_exam", False):
        if work_category == "1" or work_category is None:
            skip_vstupni = True

    if skip_vstupni:
        skipped.append("vstupni_skipped_by_position_flag")
    elif not has_vstupni:
        exam = MedicalExam(
            tenant_id=tenant_id,
            created_by=created_by,
            employee_id=employee_id,
            job_position_id=job_position_id,
            exam_category="preventivni",
            exam_type="vstupni",
            exam_date=None,
            valid_until=None,
            notes="Auto-vygenerováno — prohlídka musí být provedena.",
        )
        db.add(exam)
        created_exams.append(exam)
    else:
        skipped.append("vstupni")

    # 2) Odborné prohlídky podle JEDNOTLIVÝCH rizikových faktorů.
    #    Mapování faktor → specialties čteme z platform_settings (admin může
    #    upravit přes UI). Fallback na hardcoded mapu z medical_specialty_catalog.
    #
    #    Speciální případ: pozice s work_category='1' = bez pracovně-zdravotních
    #    rizik (vyhláška 79/2013). Odborné se negenerují, i kdyby rf_* pole
    #    obsahovala hodnoty (např. legacy data z importu). Logika je sladěná s
    #    reconcile_exams_for_employees_on_position.
    is_low_risk_position = work_category == "1"
    triggered: list[tuple[str, str, str]] = []  # (specialty, factor, rating)
    if factor_ratings and not is_low_risk_position:
        custom_mapping = await get_setting(
            db, "medical_exam.factor_to_specialties", None,
        )
        triggered = get_required_specialties_for_factors(
            factor_ratings, mapping=custom_mapping,
        )

    # Periodicity overrides z settings (per-specialty per-rating)
    custom_periodicity = await get_setting(
        db, "medical_exam.specialty_periodicity_months", None,
    )
    for specialty, source_factor, factor_rating in triggered:
        if specialty in existing_specialties:
            skipped.append(specialty)
            continue
        # Preferuj setting, fallback na hardcoded katalog
        valid_months: int | None = None
        if isinstance(custom_periodicity, dict):
            spec_rules = custom_periodicity.get(specialty)
            if isinstance(spec_rules, dict):
                m = spec_rules.get(factor_rating)
                if m is not None:
                    try:
                        valid_months = int(m)
                    except (TypeError, ValueError):
                        valid_months = None
        if valid_months is None:
            valid_months = get_periodicity_for_category(specialty, factor_rating)
        exam = MedicalExam(
            tenant_id=tenant_id,
            created_by=created_by,
            employee_id=employee_id,
            job_position_id=job_position_id,
            exam_category="odborna",
            exam_type="odborna",
            specialty=specialty,
            # Auto-generovaná: exam_date a valid_until NULL → status 'expired'.
            # OZO/lékař doplní reálné datum po provedení prohlídky.
            exam_date=None,
            valid_until=None,
            valid_months=valid_months,
            notes=(
                f"Auto-vygenerováno na základě faktoru {source_factor} = {factor_rating}. "
                "Prohlídka musí být provedena."
            ),
        )
        db.add(exam)
        created_exams.append(exam)

    # Aktualizuj timestamp poslední auto-kontroly pro throttling
    emp.last_exam_auto_check_at = datetime.now(UTC)
    await db.flush()
    return {
        "created":             len(created_exams),
        "exam_ids":            [e.id for e in created_exams],
        "skipped_specialties": skipped,
        "work_category":       work_category,
        "triggered_by_factors": [
            {"specialty": s, "factor": f, "rating": r} for s, f, r in triggered
        ],
        "rfa_present":          bool(factor_ratings),
    }


async def reconcile_exams_for_employees_on_position(
    db: AsyncSession,
    *,
    job_position_id: uuid.UUID,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> dict[str, Any]:
    """Reconcile pending lékařské prohlídky všech zaměstnanců na dané pozici.

    Volá se po změně RFA / job_position rizikových faktorů. Princip:

    1. Spočti aktuálně required specialties z RFA pozice.
    2. Pro každého aktivního zaměstnance na pozici:
       a) **Smaž** (status='archived') pending odborné prohlídky
          (`exam_type='odborna'`, `exam_date IS NULL`), jejichž specialty
          už není v required setu — riziko pominulo, prohlídka není nutná.
       b) **Přidej** nové pending prohlídky pro chybějící required specialties
          (zavolá `generate_initial_exam_requests`, který je idempotentní:
          přeskočí specialty, kde už aktivní záznam existuje).
       c) Nemažeme **completed** prohlídky (`exam_date IS NOT NULL`) ani
          vstupní prohlídku — historie zůstává, jen plán se mění.

    Vrací statistiku: počet archivovaných + nově vytvořených exams + list
    affected employees.
    """
    # Aktuální stav pozice — kategorie + RFA
    pos = (await db.execute(
        select(JobPosition).where(JobPosition.id == job_position_id),
    )).scalar_one_or_none()
    work_category = pos.work_category if pos is not None else None

    rfa = (await db.execute(
        select(RiskFactorAssessment).where(
            RiskFactorAssessment.job_position_id == job_position_id,
            RiskFactorAssessment.tenant_id == tenant_id,
        ),
    )).scalar_one_or_none()
    factor_ratings: dict[str, str | None] = {}
    if rfa is not None:
        factor_ratings = {f: getattr(rfa, f, None) for f in RF_FIELDS}

    # Speciální případ: pozice je kategorie 1 (žádná rizika).
    # Bez ohledu na RFA: zaměstnanec nepotřebuje žádné odborné prohlídky
    # (vyhláška 79/2013 — cat 1 = volitelné). Tohle pokrývá UX kdy uživatel
    # "snížil kategorii na 1" a očekává, že se vyčistí naplánované odborné.
    # Pokud user wantsmít přesto odborné, musí buď zvýšit work_category,
    # nebo nechat work_category na NULL (ne nastavit explicitně "1").
    is_low_risk_position = work_category == "1"

    custom_mapping = await get_setting(
        db, "medical_exam.factor_to_specialties", None,
    )
    triggered: list[tuple[str, str, str]] = []
    if factor_ratings and not is_low_risk_position:
        triggered = get_required_specialties_for_factors(
            factor_ratings, mapping=custom_mapping,
        )
    required_specialties = {s for s, _f, _r in triggered}

    # Zaměstnanci na pozici (aktivní)
    employees = (await db.execute(
        select(Employee).where(
            Employee.job_position_id == job_position_id,
            Employee.tenant_id == tenant_id,
            Employee.status == "active",
        ),
    )).scalars().all()

    archived_total = 0
    created_total = 0
    affected_employee_ids: list[uuid.UUID] = []

    # Skip vstupní opt-out: pozice cat 1 + flag na pozici. Když je aktivní,
    # archivujeme i pending vstupní (uživatel rozhodl, že pro tuto pozici
    # není povinná, viz JobPosition.skip_vstupni_exam).
    skip_vstupni_for_this_position = (
        pos is not None
        and getattr(pos, "skip_vstupni_exam", False)
        and (work_category == "1" or work_category is None)
    )

    for emp in employees:
        # Pending odborné prohlídky tohoto zaměstnance (exam_date IS NULL)
        pending_odborne = (await db.execute(
            select(MedicalExam).where(
                MedicalExam.employee_id == emp.id,
                MedicalExam.tenant_id == tenant_id,
                MedicalExam.status == "active",
                MedicalExam.exam_type == "odborna",
                MedicalExam.exam_date.is_(None),
            ),
        )).scalars().all()

        archived_for_this = 0
        for exam in pending_odborne:
            if exam.specialty and exam.specialty not in required_specialties:
                # Riziko pominulo — soft-delete (zachovává audit trail).
                exam.status = "archived"
                archived_for_this += 1
                archived_total += 1

        # Pending vstupní — archivuj jen pokud OZO opt-outoval pro tuto pozici
        if skip_vstupni_for_this_position:
            pending_vstupni = (await db.execute(
                select(MedicalExam).where(
                    MedicalExam.employee_id == emp.id,
                    MedicalExam.tenant_id == tenant_id,
                    MedicalExam.status == "active",
                    MedicalExam.exam_type == "vstupni",
                    MedicalExam.exam_date.is_(None),
                ),
            )).scalars().all()
            for exam in pending_vstupni:
                exam.status = "archived"
                archived_for_this += 1
                archived_total += 1

        # Idempotent regenerace nových required prohlídek (skipuje stávající
        # aktivní). Volá také reset last_exam_auto_check_at.
        result = await generate_initial_exam_requests(
            db,
            employee_id=emp.id,
            tenant_id=tenant_id,
            created_by=created_by,
        )
        new_count = result.get("created", 0)
        created_total += int(new_count)

        if archived_for_this > 0 or int(new_count) > 0:
            affected_employee_ids.append(emp.id)

    await db.flush()
    return {
        "archived":              archived_total,
        "created":               created_total,
        "affected_employees":    [str(e) for e in affected_employee_ids],
        "required_specialties":  sorted(required_specialties),
    }


async def update_medical_exam(
    db: AsyncSession, exam: MedicalExam, data: MedicalExamUpdateRequest
) -> MedicalExam:
    update_fields = data.model_dump(exclude_unset=True)
    if "job_position_id" in update_fields and update_fields["job_position_id"] is not None:
        await assert_in_tenant(
            db, JobPosition, update_fields["job_position_id"], exam.tenant_id,
            field_name="job_position_id",
        )
    for field, value in update_fields.items():
        setattr(exam, field, value)

    # Přepočítej valid_until pokud se změnil exam_date nebo valid_months
    if "valid_until" not in update_fields:
        d = exam.exam_date
        months = exam.valid_months
        if d is not None and months is not None:
            import calendar
            month = d.month + months
            year = d.year + (month - 1) // 12
            month = ((month - 1) % 12) + 1
            last_day = calendar.monthrange(year, month)[1]
            exam.valid_until = date(year, month, min(d.day, last_day))

    await db.flush()
    return exam


async def get_expiring_exams(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    days_ahead: int = 60,
) -> list[MedicalExam]:
    """Vrátí aktivní prohlídky, které vyprší do `days_ahead` dnů."""
    today = date.today()
    cutoff = today + timedelta(days=days_ahead)
    query = (
        select(MedicalExam)
        .where(
            MedicalExam.tenant_id == tenant_id,
            MedicalExam.status == "active",
            MedicalExam.valid_until >= today,
            MedicalExam.valid_until <= cutoff,
        )
        .order_by(MedicalExam.valid_until)
    )
    result = await db.execute(query)
    return list(result.scalars().all())


async def generate_exams_for_all_employees(
    db: AsyncSession,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> dict[str, Any]:
    """
    Hromadná auto-generace prohlídek napříč všemi aktivními zaměstnanci tenantu.

    Throttle: zaměstnanec, který byl zkontrolován v posledních
    AUTO_CHECK_THROTTLE_MINUTES minutách, se přeskočí (jeho prohlídky
    už jsou aktuální).

    Vrací souhrn: kolik bylo zpracováno, kolik přeskočeno (throttle),
    kolik nových prohlídek celkem vzniklo.
    """
    throttle_minutes = await _throttle_minutes(db)
    cutoff = datetime.now(UTC) - timedelta(minutes=throttle_minutes)

    employees = (await db.execute(
        select(Employee).where(
            Employee.tenant_id == tenant_id,
            Employee.status == "active",
        )
    )).scalars().all()

    processed = 0
    skipped_throttle = 0
    skipped_failed = 0
    total_created = 0

    for emp in employees:
        if (
            emp.last_exam_auto_check_at is not None
            and emp.last_exam_auto_check_at >= cutoff
        ):
            skipped_throttle += 1
            continue
        try:
            res = await generate_initial_exam_requests(
                db, emp.id, tenant_id, created_by,
            )
            processed += 1
            total_created += int(res.get("created", 0))
        except Exception:
            skipped_failed += 1
            import logging
            logging.getLogger(__name__).exception(
                "Bulk auto-generation failed for employee %s", emp.id,
            )

    return {
        "total_employees":      len(employees),
        "processed":            processed,
        "skipped_throttle":     skipped_throttle,
        "skipped_failed":       skipped_failed,
        "total_exams_created":  total_created,
        "throttle_minutes":     throttle_minutes,
    }
