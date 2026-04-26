"""Training šablony, přiřazení, pokusy, submit."""
import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

TrainingType = Literal["bozp", "po", "other"]
TrainerKind = Literal["ozo_bozp", "ozo_po", "employer"]
AssignmentStatus = Literal["pending", "completed", "expired", "revoked"]


# ── Question / test struktura ────────────────────────────────────────────────

class TestQuestion(BaseModel):
    """Otázka uložená v Training.test_questions. Správná je 'correct_answer'."""
    question: str = Field(..., min_length=1, max_length=1000)
    correct_answer: str = Field(..., min_length=1, max_length=500)
    wrong_answers: list[str] = Field(..., min_length=3, max_length=3)


# ── Training (šablona) ───────────────────────────────────────────────────────

class TrainingCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    training_type: TrainingType = "bozp"
    trainer_kind: TrainerKind = "employer"
    valid_months: int = Field(..., gt=0, le=600)
    # test_questions a pass_percentage se nastavují samostatně přes upload_test_csv
    notes: str | None = None
    # Migrace 041 — pro prezenční listinu a podpisy
    outline_text: str | None = None
    duration_hours: float | None = Field(None, ge=0, le=999)
    requires_qes: bool = False
    knowledge_test_required: bool = False


class TrainingUpdateRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    training_type: TrainingType | None = None
    trainer_kind: TrainerKind | None = None
    valid_months: int | None = Field(None, gt=0, le=600)
    pass_percentage: int | None = Field(None, ge=0, le=100)
    notes: str | None = None
    outline_text: str | None = None
    duration_hours: float | None = Field(None, ge=0, le=999)
    requires_qes: bool | None = None
    knowledge_test_required: bool | None = None


class TrainingResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID | None
    title: str
    training_type: str
    trainer_kind: str
    valid_months: int
    content_pdf_path: str | None
    # Vracíme jen boolean + count, plné otázky jen při spuštění testu
    has_test: bool
    question_count: int
    pass_percentage: int | None
    notes: str | None
    outline_text: str | None = None
    duration_hours: float | None = None
    requires_qes: bool = False
    knowledge_test_required: bool = False
    created_by: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Assignment ───────────────────────────────────────────────────────────────

class AssignmentCreateRequest(BaseModel):
    """Hromadné přiřazení: jeden training → N zaměstnanců."""
    training_id: uuid.UUID
    employee_ids: list[uuid.UUID] = Field(..., min_length=1)


class AssignmentCreateResponse(BaseModel):
    created_count: int
    skipped_existing_count: int
    errors: list[str] = []


class AssignmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    training_id: uuid.UUID
    training_title: str | None = None  # join helper, naplněno v service
    training_type: str | None = None
    training_requires_qes: bool = False  # join helper — pro signing flow
    employee_id: uuid.UUID
    employee_name: str | None = None   # join helper
    assigned_at: datetime
    deadline: datetime
    last_completed_at: datetime | None
    valid_until: date | None
    validity_status: str
    status: str
    signed_at: datetime | None = None
    signature_method: str | None = None

    model_config = {"from_attributes": True}


# ── Spuštění testu / submit ─────────────────────────────────────────────────

class TestQuestionForAttempt(BaseModel):
    """Vrácená verze otázky pro zaměstnance — odpovědi v náhodném pořadí."""
    question_index: int
    question: str
    # 4 odpovědi v náhodném pořadí (včetně správné, ale klient neví která)
    options: list[str]


class StartTestResponse(BaseModel):
    assignment_id: uuid.UUID
    training_title: str
    pass_percentage: int
    questions: list[TestQuestionForAttempt]


class AnswerSubmit(BaseModel):
    question_index: int
    chosen_answer_text: str


class SubmitTestRequest(BaseModel):
    answers: list[AnswerSubmit]


class SubmitTestResponse(BaseModel):
    attempt_id: uuid.UUID
    score_percentage: int
    passed: bool
    pass_percentage: int
    assignment: AssignmentResponse


class MarkReadRequest(BaseModel):
    """Pro training bez testu — uživatel klikne "Potvrdit absolvování"."""
    pass


# ── Test CSV import ──────────────────────────────────────────────────────────

class TestUploadResponse(BaseModel):
    question_count: int
    pass_percentage: int


# ── PDF content upload ───────────────────────────────────────────────────────

class ContentUploadResponse(BaseModel):
    content_pdf_path: str
    size_bytes: int


# ── Group assign helper ──────────────────────────────────────────────────────

class GroupAssignRequest(BaseModel):
    """Přiřadit training všem zaměstnancům odpovídajícím filtru."""
    training_id: uuid.UUID
    plant_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    job_position_id: uuid.UUID | None = None
    only_active: bool = True
