import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, Field

RatingValue = Annotated[
    str | None,
    Field(pattern=r"^(1|2|2R|3|4)$", default=None),
]

PlantStatus = Literal["active", "archived"]
WorkplaceStatus = Literal["active", "archived"]


# ── Plant ─────────────────────────────────────────────────────────────────────

class PlantCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    address: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=10)
    ico: str | None = Field(None, max_length=20)
    plant_number: str | None = Field(None, max_length=50)
    notes: str | None = None


class PlantUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    address: str | None = Field(None, max_length=255)
    city: str | None = Field(None, max_length=100)
    zip_code: str | None = Field(None, max_length=10)
    ico: str | None = Field(None, max_length=20)
    plant_number: str | None = Field(None, max_length=50)
    notes: str | None = None
    status: PlantStatus | None = None


class PlantResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    address: str | None
    city: str | None
    zip_code: str | None
    ico: str | None
    plant_number: str | None
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


# ── Workplace ─────────────────────────────────────────────────────────────────

class WorkplaceCreateRequest(BaseModel):
    plant_id: uuid.UUID
    name: str = Field(..., min_length=1, max_length=255)
    notes: str | None = None


class WorkplaceUpdateRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    notes: str | None = None
    status: WorkplaceStatus | None = None


class WorkplaceResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    plant_id: uuid.UUID
    name: str
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}


# ── RiskFactorAssessment ──────────────────────────────────────────────────────

class RiskFactorAssessmentCreateRequest(BaseModel):
    # V novém modelu: RFA je 1:1 s JobPosition. workplace_id + profese jsou
    # legacy a dopočítají se ze job_position.
    job_position_id: uuid.UUID | None = None
    workplace_id: uuid.UUID | None = None
    profese: str | None = Field(None, min_length=1, max_length=255)
    operator_names: str | None = None
    worker_count: int = Field(0, ge=0)
    women_count: int = Field(0, ge=0)

    # 13 rizikových faktorů – vše volitelné (None = neuplatňuje se)
    rf_prach:       RatingValue = None
    rf_chem:        RatingValue = None
    rf_hluk:        RatingValue = None
    rf_vibrace:     RatingValue = None
    rf_zareni:      RatingValue = None
    rf_tlak:        RatingValue = None
    rf_fyz_zatez:   RatingValue = None
    rf_prac_poloha: RatingValue = None
    rf_teplo:       RatingValue = None
    rf_chlad:       RatingValue = None
    rf_psych:       RatingValue = None
    rf_zrak:        RatingValue = None
    rf_bio:         RatingValue = None

    category_override: RatingValue = None
    sort_order: int = Field(0, ge=0)
    notes: str | None = None


class RiskFactorAssessmentUpdateRequest(BaseModel):
    profese: str | None = Field(None, min_length=1, max_length=255)
    operator_names: str | None = None
    worker_count: int | None = Field(None, ge=0)
    women_count: int | None = Field(None, ge=0)

    rf_prach:       RatingValue = None
    rf_chem:        RatingValue = None
    rf_hluk:        RatingValue = None
    rf_vibrace:     RatingValue = None
    rf_zareni:      RatingValue = None
    rf_tlak:        RatingValue = None
    rf_fyz_zatez:   RatingValue = None
    rf_prac_poloha: RatingValue = None
    rf_teplo:       RatingValue = None
    rf_chlad:       RatingValue = None
    rf_psych:       RatingValue = None
    rf_zrak:        RatingValue = None
    rf_bio:         RatingValue = None

    category_override: RatingValue = None
    sort_order: int | None = Field(None, ge=0)
    notes: str | None = None
    status: Literal["active", "archived"] | None = None


class RiskFactorAssessmentResponse(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    workplace_id: uuid.UUID | None
    job_position_id: uuid.UUID
    profese: str
    operator_names: str | None
    worker_count: int
    women_count: int

    rf_prach:       str | None
    rf_chem:        str | None
    rf_hluk:        str | None
    rf_vibrace:     str | None
    rf_zareni:      str | None
    rf_tlak:        str | None
    rf_fyz_zatez:   str | None
    rf_prac_poloha: str | None
    rf_teplo:       str | None
    rf_chlad:       str | None
    rf_psych:       str | None
    rf_zrak:        str | None
    rf_bio:         str | None

    # PDF path per faktor — frontend přes tyto cesty kontroluje,
    # zda je PDF uploadované; stažení jde přes /rfa/{id}/pdf/{factor}
    rf_prach_pdf_path:       str | None
    rf_chem_pdf_path:        str | None
    rf_hluk_pdf_path:        str | None
    rf_vibrace_pdf_path:     str | None
    rf_zareni_pdf_path:      str | None
    rf_tlak_pdf_path:        str | None
    rf_fyz_zatez_pdf_path:   str | None
    rf_prac_poloha_pdf_path: str | None
    rf_teplo_pdf_path:       str | None
    rf_chlad_pdf_path:       str | None
    rf_psych_pdf_path:       str | None
    rf_zrak_pdf_path:        str | None
    rf_bio_pdf_path:         str | None

    category_proposed: str   # computed property z modelu
    category_override: str | None
    sort_order: int
    notes: str | None
    status: str
    created_by: uuid.UUID

    model_config = {"from_attributes": True}
