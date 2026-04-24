"""Rozšíření sloupce personal_id pro Fernet-encrypted hodnoty

Revision ID: 018
Revises: 017
Create Date: 2026-04-24

employees.personal_id byl VARCHAR(20) (plain rodné číslo).
Fernet ciphertext je ~150 chars (včetně base64 overhead + HMAC + timestamp).

Změny:
- ALTER sloupec na VARCHAR(256) (safe buffer pro ciphertext).
- Stávající plaintextová data zůstávají; EncryptedString v app vrstvě
  tolerantní k InvalidToken → vrátí původní plaintext pro legacy řádky.
- Pokud chceš proaktivně všechno zašifrovat, spusť po nasazení:
  `python -m app.commands.encrypt_personal_ids`

Toto NENÍ destruktivní — je to čistě rozšíření limitu. Aplikační vrstva
(EncryptedString TypeDecorator) se stará o šifrování nových zápisů.
"""

from alembic import op

revision = "018"
down_revision = "017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE employees ALTER COLUMN personal_id TYPE VARCHAR(256)")


def downgrade() -> None:
    # POZOR: downgrade selže, pokud je v DB ciphertext (> 20 chars).
    # Před downgradem smažte/dešifrujte všechny hodnoty.
    op.execute("ALTER TABLE employees ALTER COLUMN personal_id TYPE VARCHAR(20)")
