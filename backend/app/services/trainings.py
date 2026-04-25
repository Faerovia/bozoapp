"""
Training šablony + přiřazení + testové pokusy.

Hlavní funkce:
- Training template CRUD
- Assignment create (hromadný), list per training / per employee
- Start test (randomizace odpovědí), submit (grading + update assignment)
- Test CSV parse + template
- Propagace změn v šabloně do existujících assignments: změna valid_months
  přepočítá valid_until pro všechna splněná assignment.
"""
from __future__ import annotations

import csv
import io
import random
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.storage import (
    MAX_TEST_CSV_BYTES,
    delete_file,
    save_training_pdf,
)
from app.core.validation import assert_in_tenant
from app.models.employee import Employee
from app.models.training import (
    Training,
    TrainingAssignment,
    TrainingAttempt,
)
from app.schemas.trainings import (
    AssignmentResponse,
    TestQuestion,
    TestQuestionForAttempt,
    TrainingCreateRequest,
    TrainingUpdateRequest,
)

ASSIGNMENT_DEADLINE_DAYS = 7


# ── Training template CRUD ───────────────────────────────────────────────────

async def list_trainings(
    db: AsyncSession, tenant_id: uuid.UUID
) -> list[Training]:
    result = await db.execute(
        select(Training)
        .where(Training.tenant_id == tenant_id)
        .order_by(Training.title)
    )
    return list(result.scalars().all())


async def get_training(
    db: AsyncSession, training_id: uuid.UUID, tenant_id: uuid.UUID
) -> Training | None:
    result = await db.execute(
        select(Training).where(
            Training.id == training_id,
            Training.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def create_training(
    db: AsyncSession,
    data: TrainingCreateRequest,
    tenant_id: uuid.UUID,
    created_by: uuid.UUID,
) -> Training:
    # Duplicita title v tenantu — DB constraint stejně chrání, ale explicit 409 je čitelnější
    existing = (await db.execute(
        select(Training.id).where(
            Training.tenant_id == tenant_id, Training.title == data.title
        )
    )).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Školení '{data.title}' již existuje",
        )

    training = Training(
        tenant_id=tenant_id,
        title=data.title,
        training_type=data.training_type,
        trainer_kind=data.trainer_kind,
        valid_months=data.valid_months,
        notes=data.notes,
        created_by=created_by,
    )
    db.add(training)
    await db.flush()
    return training


async def update_training(
    db: AsyncSession, training: Training, data: TrainingUpdateRequest
) -> Training:
    fields = data.model_dump(exclude_unset=True)
    old_valid_months = training.valid_months

    for k, v in fields.items():
        setattr(training, k, v)

    # Pokud se změnilo valid_months, propsat do existujících completed
    # assignments — přepočítat valid_until.
    if (
        "valid_months" in fields
        and fields["valid_months"] is not None
        and fields["valid_months"] != old_valid_months
    ):
        await _recompute_valid_until_for_training(db, training)

    await db.flush()
    return training


async def delete_training(db: AsyncSession, training: Training) -> None:
    # Cascade smaže i assignments + attempts (FK ON DELETE CASCADE)
    if training.content_pdf_path:
        delete_file(training.content_pdf_path)
    await db.delete(training)
    await db.flush()


async def _recompute_valid_until_for_training(
    db: AsyncSession, training: Training
) -> None:
    """Při změně valid_months přepočítat valid_until pro všechny completed assignments."""
    result = await db.execute(
        select(TrainingAssignment).where(
            TrainingAssignment.training_id == training.id,
            TrainingAssignment.last_completed_at.is_not(None),
        )
    )
    for ta in result.scalars():
        # Filter above ensures last_completed_at is not None; guard for mypy
        if ta.last_completed_at is None:
            continue
        ta.valid_until = _add_months(ta.last_completed_at.date(), training.valid_months)


def _add_months(d: date, months: int) -> date:
    import calendar
    month = d.month + months
    year = d.year + (month - 1) // 12
    month = ((month - 1) % 12) + 1
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(d.day, last_day))


# ── PDF content upload ───────────────────────────────────────────────────────

async def attach_pdf_content(
    db: AsyncSession, training: Training, content: bytes
) -> str:
    """Uloží PDF na disk a propojí s training. Smaže předchozí pokud byl."""
    if training.content_pdf_path:
        delete_file(training.content_pdf_path)

    if training.tenant_id is None:
        # Globální šablona — uložíme do speciálního "global" prefixu
        # přes platform-tenant pseudo-UUID. Pokud bychom chtěli oddělit,
        # přidáme samostatnou save funkci. Zatím: nepřidávat PDF na global.
        raise ValueError("PDF lze uploadnout jen u tenant-vázaných školení")
    rel_path = save_training_pdf(training.tenant_id, training.id, content)
    training.content_pdf_path = rel_path
    await db.flush()
    return rel_path


# ── Test CSV ─────────────────────────────────────────────────────────────────

def parse_test_csv(content: bytes) -> list[TestQuestion]:
    """
    Parsuje CSV: první sloupec = otázka, sloupce 2–5 = 4 odpovědi (první = správná).
    Vrací seznam TestQuestion. Validace 5–25 otázek.
    """
    if len(content) > MAX_TEST_CSV_BYTES:
        raise ValueError(f"CSV je příliš velké (max {MAX_TEST_CSV_BYTES // 1024} KB)")

    try:
        text = content.decode("utf-8").lstrip("\ufeff")
    except UnicodeDecodeError:
        text = content.decode("cp1250")

    # Auto-detect delimiter. csv.Sniffer.sniff() vrací `type[csv.Dialect]`
    # (třídu, ne instanci); csv.reader(dialect=...) akceptuje obojí.
    dialect: type[csv.Dialect]
    try:
        dialect = csv.Sniffer().sniff(text[:1024], delimiters=",;")
    except csv.Error:
        dialect = csv.excel

    reader = csv.reader(io.StringIO(text), dialect=dialect)

    questions: list[TestQuestion] = []
    for row_num, row in enumerate(reader, start=1):
        if not row or not any(c.strip() for c in row):
            continue  # prázdný řádek

        # Skip header — pokud první buňka obsahuje typické slovo pro otázku.
        # Detekce je tolerantní k diakritice (otázka/otazka) i k anglickému zápisu.
        if row_num == 1:
            first = row[0].strip().lower()
            header_markers = ("otazka", "otázka", "question", "q1", "q ")
            if any(m in first for m in header_markers):
                continue

        if len(row) < 5:
            raise ValueError(
                f"Řádek {row_num}: očekávám 5 sloupců (otázka + 4 odpovědi), nalezeno {len(row)}"
            )

        question_text = row[0].strip()
        if not question_text:
            raise ValueError(f"Řádek {row_num}: prázdná otázka")

        answers = [row[i].strip() for i in range(1, 5)]
        if not all(answers):
            raise ValueError(f"Řádek {row_num}: některá odpověď je prázdná")

        questions.append(TestQuestion(
            question=question_text,
            correct_answer=answers[0],
            wrong_answers=answers[1:],
        ))

    if len(questions) < 5:
        raise ValueError(
            f"Test musí mít minimálně 5 otázek (nalezeno {len(questions)})"
        )
    if len(questions) > 25:
        raise ValueError(
            f"Test smí mít maximálně 25 otázek (nalezeno {len(questions)})"
        )

    return questions


def generate_test_csv_template() -> str:
    """Vzor CSV pro test upload."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["otazka", "spravna_odpoved", "spatna_1", "spatna_2", "spatna_3"])
    w.writerow([
        "Jaká je maximální povolená hmotnost břemene pro pracovní zvedání?",
        "50 kg",
        "30 kg",
        "100 kg",
        "neomezeno",
    ])
    w.writerow([
        "Co dělat při úrazu na pracovišti?",
        "Zajistit první pomoc a oznámit nadřízenému",
        "Pokračovat v práci",
        "Dopsat do deníku až po směně",
        "Zavolat jen rodinu",
    ])
    w.writerow([
        "Jak často se školí BOZP pro rizikové pracoviště?",
        "Dle zákoníku práce a kategorizace práce",
        "Jednou za život",
        "Nikdy",
        "Jen při nástupu",
    ])
    w.writerow([
        "Kdo je odpovědný za dodržování BOZP?",
        "Zaměstnavatel i zaměstnanec",
        "Jen ředitel",
        "Jen externí OZO",
        "Nikdo",
    ])
    w.writerow([
        "Co je to OOPP?",
        "Osobní ochranný pracovní prostředek",
        "Odbor pracovní pozice",
        "Ochrana před prací",
        "Oficiální povinný předpis",
    ])
    return "\ufeff" + buf.getvalue()


async def set_test(
    db: AsyncSession,
    training: Training,
    questions: list[TestQuestion],
    pass_percentage: int,
) -> None:
    """Nastaví test_questions + pass_percentage na šabloně."""
    if not (0 <= pass_percentage <= 100):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="pass_percentage musí být 0–100",
        )
    training.test_questions = [q.model_dump() for q in questions]
    training.pass_percentage = pass_percentage
    await db.flush()


async def remove_test(db: AsyncSession, training: Training) -> None:
    training.test_questions = None
    training.pass_percentage = None
    await db.flush()


# ── Assignment ───────────────────────────────────────────────────────────────

async def create_assignments(
    db: AsyncSession,
    *,
    training: Training,
    employee_ids: list[uuid.UUID],
    tenant_id: uuid.UUID,
    assigned_by: uuid.UUID,
) -> tuple[int, int, list[str]]:
    """
    Vytvoří TrainingAssignment pro každé employee_id. Vrací (created, skipped, errors).
    - skipped: zaměstnanec už má tuto šablonu přiřazenou (unique constraint)
    """
    created = 0
    skipped = 0
    errors: list[str] = []

    for emp_id in employee_ids:
        try:
            await assert_in_tenant(
                db, Employee, emp_id, tenant_id, field_name="employee_id"
            )
        except HTTPException as e:
            errors.append(f"{emp_id}: {e.detail}")
            continue

        # Zkontrolovat duplicitu
        existing = (await db.execute(
            select(TrainingAssignment.id).where(
                TrainingAssignment.training_id == training.id,
                TrainingAssignment.employee_id == emp_id,
            )
        )).scalar_one_or_none()

        if existing is not None:
            skipped += 1
            continue

        now = datetime.now(UTC)
        db.add(TrainingAssignment(
            tenant_id=tenant_id,
            training_id=training.id,
            employee_id=emp_id,
            assigned_at=now,
            deadline=now + timedelta(days=ASSIGNMENT_DEADLINE_DAYS),
            status="pending",
            assigned_by=assigned_by,
        ))
        created += 1

    await db.flush()
    return created, skipped, errors


async def list_assignments_for_training(
    db: AsyncSession, training_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[TrainingAssignment]:
    result = await db.execute(
        select(TrainingAssignment).where(
            TrainingAssignment.training_id == training_id,
            TrainingAssignment.tenant_id == tenant_id,
        )
    )
    return list(result.scalars().all())


async def list_assignments_for_employee(
    db: AsyncSession, employee_id: uuid.UUID, tenant_id: uuid.UUID
) -> list[TrainingAssignment]:
    result = await db.execute(
        select(TrainingAssignment)
        .where(
            TrainingAssignment.employee_id == employee_id,
            TrainingAssignment.tenant_id == tenant_id,
        )
        .order_by(TrainingAssignment.assigned_at.desc())
    )
    return list(result.scalars().all())


async def get_assignment(
    db: AsyncSession, assignment_id: uuid.UUID, tenant_id: uuid.UUID
) -> TrainingAssignment | None:
    result = await db.execute(
        select(TrainingAssignment).where(
            TrainingAssignment.id == assignment_id,
            TrainingAssignment.tenant_id == tenant_id,
        )
    )
    return result.scalar_one_or_none()


async def revoke_assignment(db: AsyncSession, assignment: TrainingAssignment) -> None:
    assignment.status = "revoked"
    await db.flush()


# ── Test flow: start / submit ────────────────────────────────────────────────

def prepare_test_for_attempt(
    questions: list[dict[str, Any]],
) -> list[TestQuestionForAttempt]:
    """
    Pro test attempt: zamíchej pořadí odpovědí u každé otázky.
    Klient nemůže z pořadí odvodit, která je správná.
    """
    out: list[TestQuestionForAttempt] = []
    for idx, q in enumerate(questions):
        options = [q["correct_answer"], *q["wrong_answers"]]
        random.shuffle(options)
        out.append(TestQuestionForAttempt(
            question_index=idx,
            question=q["question"],
            options=options,
        ))
    return out


async def submit_attempt(
    db: AsyncSession,
    *,
    assignment: TrainingAssignment,
    training: Training,
    answers: list[dict[str, Any]],  # [{question_index, chosen_answer_text}]
) -> TrainingAttempt:
    """
    Vyhodnotí test. Pokud score >= pass_percentage, update assignment
    (last_completed_at + valid_until).
    """
    if not training.test_questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="K tomuto školení není přiložen test",
        )
    if training.pass_percentage is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Školení má test ale chybí pass_percentage (inkonzistence)",
        )

    questions = training.test_questions
    answers_by_idx = {a["question_index"]: a["chosen_answer_text"] for a in answers}

    correct_count = 0
    audit_answers: list[dict[str, Any]] = []
    for idx, q in enumerate(questions):
        chosen = answers_by_idx.get(idx, "")
        is_correct = chosen == q["correct_answer"]
        if is_correct:
            correct_count += 1
        audit_answers.append({
            "question_index": idx,
            "chosen_answer_text": chosen,
            "correct": is_correct,
        })

    score = round((correct_count / len(questions)) * 100)
    passed = score >= training.pass_percentage

    attempt = TrainingAttempt(
        tenant_id=assignment.tenant_id,
        assignment_id=assignment.id,
        score_percentage=score,
        passed=passed,
        answers=audit_answers,
    )
    db.add(attempt)

    if passed:
        now = datetime.now(UTC)
        assignment.last_completed_at = now
        assignment.valid_until = _add_months(now.date(), training.valid_months)
        assignment.status = "completed"

    await db.flush()
    return attempt


async def mark_assignment_read(
    db: AsyncSession,
    *,
    assignment: TrainingAssignment,
    training: Training,
) -> None:
    """Training bez testu — zaměstnanec klikne "Potvrdit přečtení"."""
    if training.test_questions:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Toto školení vyžaduje absolvování testu",
        )
    now = datetime.now(UTC)
    assignment.last_completed_at = now
    assignment.valid_until = _add_months(now.date(), training.valid_months)
    assignment.status = "completed"
    await db.flush()


# ── Helpers pro response s joins ─────────────────────────────────────────────

async def enrich_assignment(
    db: AsyncSession, a: TrainingAssignment
) -> AssignmentResponse:
    """Naplní training_title, employee_name pro response."""
    t = (await db.execute(
        select(Training).where(Training.id == a.training_id)
    )).scalar_one_or_none()
    e = (await db.execute(
        select(Employee).where(Employee.id == a.employee_id)
    )).scalar_one_or_none()

    r = AssignmentResponse.model_validate(a)
    r.validity_status = a.validity_status
    if t:
        r.training_title = t.title
        r.training_type = t.training_type
    if e:
        r.employee_name = f"{e.first_name} {e.last_name}".strip()
    return r


async def latest_passed_attempt(
    db: AsyncSession, assignment_id: uuid.UUID
) -> TrainingAttempt | None:
    result = await db.execute(
        select(TrainingAttempt)
        .where(
            TrainingAttempt.assignment_id == assignment_id,
            TrainingAttempt.passed == True,  # noqa: E712
        )
        .order_by(TrainingAttempt.attempted_at.desc())
    )
    return result.scalars().first()
