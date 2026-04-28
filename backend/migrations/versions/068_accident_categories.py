"""Standardizované kategorie zdroje a příčiny úrazu

Revision ID: 068
Revises: 067
Create Date: 2026-04-28

Přidává standardizované kategorizační kódy pro zdroj úrazu (6 hodnot)
a příčinu úrazu (10 hodnot) dle metodiky SÚIP. Stávající textová pole
`injury_source` a `injury_cause` zůstávají jako popisové pole pro detail.

Pro nové úrazy povinné na úrovni Pydantic schémat, v DB nullable kvůli
historickým záznamům před migrací 068.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


SOURCE_CATEGORIES = (
    "vehicles", "machines", "tools",
    "hazardous_substances", "persons_animals", "work_environment",
)

CAUSE_CATEGORIES = (
    "workplace_defect", "missing_protection", "oopp_misuse",
    "source_defect", "poor_organization", "high_risk_work",
    "personal_factors", "unsafe_behavior", "third_party", "unforeseen",
)


def upgrade() -> None:
    op.add_column(
        "accident_reports",
        sa.Column("injury_source_category", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "accident_reports_source_category_valid",
        "accident_reports",
        "injury_source_category IS NULL OR injury_source_category IN "
        + "(" + ",".join(f"'{c}'" for c in SOURCE_CATEGORIES) + ")",
    )
    op.create_index(
        "ix_accident_reports_source_category",
        "accident_reports",
        ["tenant_id", "injury_source_category"],
    )

    op.add_column(
        "accident_reports",
        sa.Column("injury_cause_category", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "accident_reports_cause_category_valid",
        "accident_reports",
        "injury_cause_category IS NULL OR injury_cause_category IN "
        + "(" + ",".join(f"'{c}'" for c in CAUSE_CATEGORIES) + ")",
    )
    op.create_index(
        "ix_accident_reports_cause_category",
        "accident_reports",
        ["tenant_id", "injury_cause_category"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_accident_reports_cause_category", table_name="accident_reports",
    )
    op.drop_constraint(
        "accident_reports_cause_category_valid",
        "accident_reports",
        type_="check",
    )
    op.drop_column("accident_reports", "injury_cause_category")

    op.drop_index(
        "ix_accident_reports_source_category", table_name="accident_reports",
    )
    op.drop_constraint(
        "accident_reports_source_category_valid",
        "accident_reports",
        type_="check",
    )
    op.drop_column("accident_reports", "injury_source_category")
