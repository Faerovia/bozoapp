"""Schémata pro OZO multi-client overview."""

import uuid

from pydantic import BaseModel


class ClientMetrics(BaseModel):
    expiring_trainings: int
    due_revisions: int
    overdue_revisions: int
    expiring_medical_exams: int
    draft_accident_reports: int
    expiring_oopp: int


class ClientOverview(BaseModel):
    tenant_id: uuid.UUID
    tenant_name: str
    role: str
    is_default: bool
    metrics: ClientMetrics
    total_actions: int
