"""Evidence osobních ochranných pracovních prostředků (OOPP)

Revision ID: 006
Revises: 005
Create Date: 2026-04-23

Legislativní základ:
- Zákoník práce §104 – povinnost poskytnout OOPP
- NV 495/2001 Sb. – podmínky a rozsah OOPP
- NV 21/2003 Sb. – technické požadavky na OOPP

Datový model:
- Každý záznam = jeden výdej OOPP jednomu zaměstnanci
- employee_id FK (zaměstnanci v systému) + employee_name VARCHAR (i externisté)
- valid_months NULL = OOPP bez expiry (brýle, sluchátka atd.)
- valid_until = issued_at + valid_months nebo ruční override
- Kategorie dle NV 495/2001 příloha
"""

from alembic import op

revision: str = "006"
down_revision: str = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE oopp_assignments (
            id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            tenant_id       UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,

            -- Příjemce OOPP
            employee_id     UUID REFERENCES users(id) ON DELETE RESTRICT,
            -- NULL pokud jde o externistu; povinné: alespoň employee_name
            employee_name   VARCHAR(255) NOT NULL,

            -- Co bylo vydáno
            item_name       VARCHAR(255) NOT NULL,
            oopp_type       VARCHAR(50) NOT NULL DEFAULT 'other',
            -- hodnoty: head_protection | eye_protection | hearing_protection |
            --          respiratory_protection | hand_protection | foot_protection |
            --          fall_protection | body_protection | skin_protection |
            --          visibility | other

            -- Vydání
            issued_at       DATE NOT NULL,
            quantity        SMALLINT NOT NULL DEFAULT 1 CHECK (quantity > 0),
            size_spec       VARCHAR(50),   -- velikost (M, L, 42, ...) – "size" je rezervované slovo v SQL
            serial_number   VARCHAR(100),  -- výrobní číslo / šarže

            -- Platnost
            valid_months    SMALLINT CHECK (valid_months > 0),
            valid_until     DATE,
            -- NULL: OOPP bez expiry nebo valid_months nebyl zadán

            -- Doplňující informace
            notes           TEXT,

            -- Správa záznamu
            status          VARCHAR(20) NOT NULL DEFAULT 'active',
            -- hodnoty: active | archived

            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    # Indexy pro typické dotazy
    op.execute("CREATE INDEX idx_oopp_tenant ON oopp_assignments(tenant_id)")
    op.execute("CREATE INDEX idx_oopp_employee ON oopp_assignments(tenant_id, employee_id) WHERE employee_id IS NOT NULL")
    op.execute("CREATE INDEX idx_oopp_valid_until ON oopp_assignments(tenant_id, valid_until) WHERE valid_until IS NOT NULL")
    op.execute("CREATE INDEX idx_oopp_type ON oopp_assignments(tenant_id, oopp_type)")

    # RLS – tenant izolace
    op.execute("ALTER TABLE oopp_assignments ENABLE ROW LEVEL SECURITY")

    op.execute("""
        CREATE POLICY tenant_isolation ON oopp_assignments
            USING (
                tenant_id = current_setting('app.current_tenant_id', TRUE)::UUID
            )
    """)

    op.execute("""
        CREATE POLICY superadmin_bypass ON oopp_assignments
            USING (current_setting('app.is_superadmin', TRUE) = 'true')
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS oopp_assignments CASCADE")
