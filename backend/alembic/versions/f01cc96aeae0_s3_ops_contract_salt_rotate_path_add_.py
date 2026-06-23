"""S3-OPS-CONTRACT-SALT-ROTATE-PATH add salt_version + WORM guard (ADR-0046 r8 plan D)

Revision ID: f01cc96aeae0
Revises: a07229409127
Create Date: 2026-06-23 07:30:42.981182

ADR-0046 r8 (方案 D: 存量不动 + 仅新合同轮换):

- service_contracts 加 salt_version 列 (SMALLINT NOT NULL DEFAULT 1)。
  patient_pseudonym_hash 生成时用的 salt 版本号, 纯审计/取证溯源。
  不进 contract_hash 计算 (不入 _HASH_INPUTS_REQUIRED_KEYS), 不参与
  recompute 验证。存量行靠 server_default 1 自动填值, 零 UPDATE
  (方案 D 存量不动, 保 WORM)。

- immutable_guard trigger CREATE OR REPLACE: 在原 8 immutable 字段
  (order_id / template_version / contract_hash / hash_inputs /
  storage_blob_path / generated_at / is_immutable / created_at) 基础上
  加 salt_version → 9 字段。salt_version 创建后不可改 (防篡改溯源)。
  注意: 这是给 salt_version 列 *加* WORM 守护, 不是给 pseudonym_hash
  加豁免 (已废方案 A)。

  Field list 必须与 app/models/service_contract.py::IMMUTABLE_FIELDS (9)
  + test_contract_state_machine.py::TestImmutableFieldsSentinel 一致;
  漂移由 sentinel fail-fast。

  SQLite 无 PL/pgSQL — 该路径 immutable 由 PG-only smoke test 覆盖
  (与现有 immutable trigger 测试同模式)。

加列骨架由 alembic autogenerate 产生 (model ground truth); trigger
CREATE OR REPLACE 手补 (autogen 不出 trigger DDL)。
"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f01cc96aeae0'
down_revision: Union[str, None] = 'a07229409127'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Trigger body WITH salt_version guard (9 immutable fields).
# CREATE OR REPLACE — function 替换即可, trigger 绑定 (BEFORE UPDATE) 不变,
# 无需 drop/recreate trigger。
# ---------------------------------------------------------------------------
_TRIGGER_BODY_WITH_SALT_VERSION = """
CREATE OR REPLACE FUNCTION service_contracts_immutable_guard()
RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.order_id IS DISTINCT FROM NEW.order_id) THEN
        RAISE EXCEPTION 'service_contracts.order_id is immutable (ADR-0046 §3.3 layer 3)';
    END IF;
    IF (OLD.template_version IS DISTINCT FROM NEW.template_version) THEN
        RAISE EXCEPTION 'service_contracts.template_version is immutable';
    END IF;
    IF (OLD.contract_hash IS DISTINCT FROM NEW.contract_hash) THEN
        RAISE EXCEPTION 'service_contracts.contract_hash is immutable';
    END IF;
    IF (OLD.hash_inputs IS DISTINCT FROM NEW.hash_inputs) THEN
        RAISE EXCEPTION 'service_contracts.hash_inputs is immutable';
    END IF;
    -- storage_blob_path: NULL → non-NULL allowed (first write); non-NULL → other rejected
    IF (OLD.storage_blob_path IS NOT NULL
        AND OLD.storage_blob_path IS DISTINCT FROM NEW.storage_blob_path) THEN
        RAISE EXCEPTION 'service_contracts.storage_blob_path is immutable once set';
    END IF;
    -- generated_at: NULL → non-NULL allowed (first generation); non-NULL → other rejected
    IF (OLD.generated_at IS NOT NULL
        AND OLD.generated_at IS DISTINCT FROM NEW.generated_at) THEN
        RAISE EXCEPTION 'service_contracts.generated_at is immutable once set';
    END IF;
    IF (OLD.is_immutable IS DISTINCT FROM NEW.is_immutable) THEN
        RAISE EXCEPTION 'service_contracts.is_immutable cannot be flipped';
    END IF;
    IF (OLD.created_at IS DISTINCT FROM NEW.created_at) THEN
        RAISE EXCEPTION 'service_contracts.created_at is immutable';
    END IF;
    -- S3-OPS-CONTRACT-SALT-ROTATE-PATH / ADR-0046 r8 (方案 D): salt_version
    -- 创建后 immutable (防篡改 salt 取证溯源记录)。
    IF (OLD.salt_version IS DISTINCT FROM NEW.salt_version) THEN
        RAISE EXCEPTION 'service_contracts.salt_version is immutable (ADR-0046 r8 plan D)';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

# Original trigger body (8 fields, WITHOUT salt_version) — for downgrade.
# 与 d5e6f7a8b9c1 migration 的 _TRIGGER_BODY_SQL 一致。
_TRIGGER_BODY_WITHOUT_SALT_VERSION = """
CREATE OR REPLACE FUNCTION service_contracts_immutable_guard()
RETURNS TRIGGER AS $$
BEGIN
    IF (OLD.order_id IS DISTINCT FROM NEW.order_id) THEN
        RAISE EXCEPTION 'service_contracts.order_id is immutable (ADR-0046 §3.3 layer 3)';
    END IF;
    IF (OLD.template_version IS DISTINCT FROM NEW.template_version) THEN
        RAISE EXCEPTION 'service_contracts.template_version is immutable';
    END IF;
    IF (OLD.contract_hash IS DISTINCT FROM NEW.contract_hash) THEN
        RAISE EXCEPTION 'service_contracts.contract_hash is immutable';
    END IF;
    IF (OLD.hash_inputs IS DISTINCT FROM NEW.hash_inputs) THEN
        RAISE EXCEPTION 'service_contracts.hash_inputs is immutable';
    END IF;
    IF (OLD.storage_blob_path IS NOT NULL
        AND OLD.storage_blob_path IS DISTINCT FROM NEW.storage_blob_path) THEN
        RAISE EXCEPTION 'service_contracts.storage_blob_path is immutable once set';
    END IF;
    IF (OLD.generated_at IS NOT NULL
        AND OLD.generated_at IS DISTINCT FROM NEW.generated_at) THEN
        RAISE EXCEPTION 'service_contracts.generated_at is immutable once set';
    END IF;
    IF (OLD.is_immutable IS DISTINCT FROM NEW.is_immutable) THEN
        RAISE EXCEPTION 'service_contracts.is_immutable cannot be flipped';
    END IF;
    IF (OLD.created_at IS DISTINCT FROM NEW.created_at) THEN
        RAISE EXCEPTION 'service_contracts.created_at is immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('service_contracts', sa.Column('salt_version', sa.SmallInteger(), server_default='1', nullable=False, comment="patient_pseudonym_hash 生成时用的 salt 版本号 (ADR-0046 r8 方案 D). 纯审计/取证溯源 — 回答'这行当年用第几版 salt'。 不进 contract_hash 计算 (不入 hash_inputs), 不参与 recompute 验证。 创建后 immutable (加入 IMMUTABLE_FIELDS + trigger 守护, 防篡改溯源)。 存量行靠 DEFAULT 1 自动填值, 无需 UPDATE (方案 D 存量不动)。"))  # noqa: E501
    # ### end Alembic commands ###

    # ----- Manual addition: extend immutable_guard trigger with salt_version -----
    # (autogen 不出 trigger DDL; SQLite 无 PL/pgSQL → app 层不需此 guard,
    #  immutable 由 PG-only smoke test 覆盖)
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(_TRIGGER_BODY_WITH_SALT_VERSION)


def downgrade() -> None:
    # ----- Reverse manual addition first: restore 8-field trigger body -----
    # 必须先还原 trigger (去掉 salt_version 检查) 再 drop 列, 否则 trigger
    # function 体引用即将被删的 NEW.salt_version → 后续 UPDATE 崩。
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(_TRIGGER_BODY_WITHOUT_SALT_VERSION)

    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('service_contracts', 'salt_version')
    # ### end Alembic commands ###
