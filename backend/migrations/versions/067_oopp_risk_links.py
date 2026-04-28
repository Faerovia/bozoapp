"""OOPP standardní slovník: body_part_code v úrazu + oopp_risk_column v RA

Revision ID: 067
Revises: 066
Create Date: 2026-04-28

Sjednocuje slovník napříč moduly Účaz/RA/OOPP na NV 390/2021 Příloha 2:
- accident_reports.injured_body_part_code  CHAR(1) IN ('A'..'N')
- risk_assessments.oopp_risk_column        SMALLINT 1..26

Stará pole zůstávají:
- accident_reports.injured_body_part  → popisové pole "Detail zranění"
- risk_assessments.hazard_category    → legacy, mapping s oopp_risk_column zajistí frontend

Pro existující data (demo) jsou nové sloupce NULL — uživatel přepíše ručně.
Pro nové záznamy jsou na úrovni Pydantic schémat povinné.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "067"
down_revision = "066"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- accident_reports.injured_body_part_code -------------------------
    op.add_column(
        "accident_reports",
        sa.Column("injured_body_part_code", sa.String(length=1), nullable=True),
    )
    op.create_check_constraint(
        "accident_reports_body_part_code_valid",
        "accident_reports",
        "injured_body_part_code IS NULL OR injured_body_part_code IN "
        "('A','B','C','D','E','F','G','H','I','J','K','L','M','N')",
    )
    op.create_index(
        "ix_accident_reports_body_part_code",
        "accident_reports",
        ["tenant_id", "injured_body_part_code"],
    )

    # --- risk_assessments.oopp_risk_column -------------------------------
    op.add_column(
        "risk_assessments",
        sa.Column("oopp_risk_column", sa.SmallInteger(), nullable=True),
    )
    op.create_check_constraint(
        "risk_assessments_oopp_risk_column_valid",
        "risk_assessments",
        "oopp_risk_column IS NULL OR oopp_risk_column BETWEEN 1 AND 26",
    )
    op.create_index(
        "ix_risk_assessments_oopp_risk_column",
        "risk_assessments",
        ["tenant_id", "oopp_risk_column"],
    )


def downgrade() -> None:
    op.drop_index("ix_risk_assessments_oopp_risk_column", table_name="risk_assessments")
    op.drop_constraint(
        "risk_assessments_oopp_risk_column_valid", "risk_assessments", type_="check",
    )
    op.drop_column("risk_assessments", "oopp_risk_column")

    op.drop_index("ix_accident_reports_body_part_code", table_name="accident_reports")
    op.drop_constraint(
        "accident_reports_body_part_code_valid", "accident_reports", type_="check",
    )
    op.drop_column("accident_reports", "injured_body_part_code")
