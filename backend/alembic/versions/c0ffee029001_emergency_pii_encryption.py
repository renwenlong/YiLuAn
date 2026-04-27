"""emergency_pii_encryption_adr_0029

Revision ID: c0ffee029001
Revises: a1d0c0de0030
Create Date: 2026-04-27

ADR-0029 / D-043 紧急联系人 PII 加密落地：

- ``emergency_contacts.phone`` (VARCHAR(20) 明文)
    → ``phone_encrypted`` (LargeBinary, AES-256-GCM 密文)
    + ``phone_hash`` (CHAR(64), HMAC-SHA256 hex, indexed)
- ``emergency_events.contact_called`` (VARCHAR(50) 明文)
    → ``contact_called_encrypted`` (LargeBinary)
    + ``contact_called_hash`` (CHAR(64), indexed)
- ``emergency_contacts.expires_at`` (cron 90d grace 删除)
- ``emergency_events.expires_at``  (cron 180d 自动清理)

数据迁移：升级时把已有的明文逐行加密回填后再 drop 旧列；降级时把
明文从密文里反向写回（依然依赖 envelope key），保证可逆 / 不丢数据。

注意：本迁移会调用 ``app.core.pii.encrypt_phone`` / ``decrypt_phone``，
所以执行 alembic 时必须保证 ``PII_ENVELOPE_KEY`` / ``PII_HASH_SALT`` 已
配置（dev 默认值即可）。
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c0ffee029001"
down_revision = "a1d0c0de0030"
branch_labels = None
depends_on = None


_BATCH_SIZE = 1000


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _backfill_encrypt(table: str, plaintext_col: str, ct_col: str, hash_col: str) -> None:
    """读出 plaintext_col → 加密回填 ct_col + hash_col。"""
    from app.core.pii import encrypt_phone, phone_hash

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, {plaintext_col} FROM {table} WHERE {plaintext_col} IS NOT NULL")
    ).fetchall()
    for row in rows:
        rid, plain = row[0], row[1]
        if plain is None:
            continue
        bind.execute(
            sa.text(
                f"UPDATE {table} SET {ct_col} = :ct, {hash_col} = :h WHERE id = :id"
            ),
            {"ct": encrypt_phone(plain), "h": phone_hash(plain), "id": rid},
        )


def _backfill_decrypt(table: str, ct_col: str, plaintext_col: str) -> None:
    """读出 ct_col → 解密回填 plaintext_col（downgrade 用）。"""
    from app.core.pii import decrypt_phone

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(f"SELECT id, {ct_col} FROM {table} WHERE {ct_col} IS NOT NULL")
    ).fetchall()
    for row in rows:
        rid, ct = row[0], row[1]
        if ct is None:
            continue
        bind.execute(
            sa.text(f"UPDATE {table} SET {plaintext_col} = :p WHERE id = :id"),
            {"p": decrypt_phone(ct), "id": rid},
        )


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------
def upgrade() -> None:
    # ---- emergency_contacts ----
    op.add_column(
        "emergency_contacts",
        sa.Column("phone_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "emergency_contacts",
        sa.Column("phone_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "emergency_contacts",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    _backfill_encrypt(
        "emergency_contacts",
        plaintext_col="phone",
        ct_col="phone_encrypted",
        hash_col="phone_hash",
    )

    # 把新列改为 NOT NULL（数据回填后）
    if _is_postgres():
        op.alter_column("emergency_contacts", "phone_encrypted", nullable=False)
        op.alter_column("emergency_contacts", "phone_hash", nullable=False)
        op.drop_column("emergency_contacts", "phone")
    else:
        with op.batch_alter_table("emergency_contacts") as batch_op:
            batch_op.alter_column("phone_encrypted", nullable=False)
            batch_op.alter_column("phone_hash", nullable=False)
            batch_op.drop_column("phone")

    op.create_index(
        "ix_emergency_contacts_phone_hash",
        "emergency_contacts",
        ["phone_hash"],
    )
    op.create_index(
        "ix_emergency_contacts_expires_at",
        "emergency_contacts",
        ["expires_at"],
    )

    # ---- emergency_events ----
    op.add_column(
        "emergency_events",
        sa.Column("contact_called_encrypted", sa.LargeBinary(), nullable=True),
    )
    op.add_column(
        "emergency_events",
        sa.Column("contact_called_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "emergency_events",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )

    _backfill_encrypt(
        "emergency_events",
        plaintext_col="contact_called",
        ct_col="contact_called_encrypted",
        hash_col="contact_called_hash",
    )

    if _is_postgres():
        op.alter_column("emergency_events", "contact_called_encrypted", nullable=False)
        op.alter_column("emergency_events", "contact_called_hash", nullable=False)
        op.drop_column("emergency_events", "contact_called")
    else:
        with op.batch_alter_table("emergency_events") as batch_op:
            batch_op.alter_column("contact_called_encrypted", nullable=False)
            batch_op.alter_column("contact_called_hash", nullable=False)
            batch_op.drop_column("contact_called")

    op.create_index(
        "ix_emergency_events_contact_called_hash",
        "emergency_events",
        ["contact_called_hash"],
    )
    op.create_index(
        "ix_emergency_events_expires_at",
        "emergency_events",
        ["expires_at"],
    )


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------
def downgrade() -> None:
    # ---- emergency_events ----
    op.drop_index("ix_emergency_events_expires_at", table_name="emergency_events")
    op.drop_index(
        "ix_emergency_events_contact_called_hash", table_name="emergency_events"
    )

    op.add_column(
        "emergency_events",
        sa.Column("contact_called", sa.String(length=50), nullable=True),
    )
    _backfill_decrypt(
        "emergency_events",
        ct_col="contact_called_encrypted",
        plaintext_col="contact_called",
    )

    if _is_postgres():
        op.alter_column("emergency_events", "contact_called", nullable=False)
        op.drop_column("emergency_events", "contact_called_encrypted")
        op.drop_column("emergency_events", "contact_called_hash")
        op.drop_column("emergency_events", "expires_at")
    else:
        with op.batch_alter_table("emergency_events") as batch_op:
            batch_op.alter_column("contact_called", nullable=False)
            batch_op.drop_column("contact_called_encrypted")
            batch_op.drop_column("contact_called_hash")
            batch_op.drop_column("expires_at")

    # ---- emergency_contacts ----
    op.drop_index(
        "ix_emergency_contacts_expires_at", table_name="emergency_contacts"
    )
    op.drop_index(
        "ix_emergency_contacts_phone_hash", table_name="emergency_contacts"
    )

    op.add_column(
        "emergency_contacts",
        sa.Column("phone", sa.String(length=20), nullable=True),
    )
    _backfill_decrypt(
        "emergency_contacts",
        ct_col="phone_encrypted",
        plaintext_col="phone",
    )

    if _is_postgres():
        op.alter_column("emergency_contacts", "phone", nullable=False)
        op.drop_column("emergency_contacts", "phone_encrypted")
        op.drop_column("emergency_contacts", "phone_hash")
        op.drop_column("emergency_contacts", "expires_at")
    else:
        with op.batch_alter_table("emergency_contacts") as batch_op:
            batch_op.alter_column("phone", nullable=False)
            batch_op.drop_column("phone_encrypted")
            batch_op.drop_column("phone_hash")
            batch_op.drop_column("expires_at")
