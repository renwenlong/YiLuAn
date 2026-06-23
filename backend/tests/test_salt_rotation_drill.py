"""AC#6 — contract pseudonym salt 轮换演练 (S3-OPS-CONTRACT-SALT-ROTATE-PATH / ADR-0046 r8 方案 D).

方案 D 核心实证: **存量不动 + 仅新合同轮换**。本演练用纯逻辑 (monkeypatch 切
salt) 证明完整轮换语义, 不需 PG (hash 是纯函数, salt 切换通过 settings)。

演练剧本 (AC#6):
  ① 造存量合同 (salt_version=1, 用 OLD salt 算 pseudonym_hash + 冻结 snapshot)
  ② 切 PRIMARY 为 NEW salt + version 递增到 2
  ③ 造新合同 (同患者同 last4)
  ④ 断言:
     - 新合同 pseudonym_hash 用新 salt (与 OLD salt 算的不同 → 轮换生效)
     - salt_version 递增 (1 → 2)
     - 存量合同 recompute_contract_hash 仍 pass (snapshot 冻结值, 不受轮换影响)
     - 存量 contract_hash 零变化 (WORM 保持)
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.services import contract_hash
from app.services.contract_hash import (
    compute_patient_pseudonym_hash,
    generate_contract_hash_at_commit_time,
    recompute_contract_hash,
)

OLD_SALT = "old-salt-v1-2cQ8mP4xJ9zR5kL7nW3"
NEW_SALT = "new-salt-v2-7hG2dF8sA1qE4rT6yU9"

PATIENT_NAME = "张三"
ID_CARD_LAST4 = "1234"
ORDER_ID_EXISTING = "ord_existing_01HXX1234567890ABCDEF"
ORDER_ID_NEW = "ord_new_01HXX1234567890ABCDEFGHI"
SERVICE_PKG_ID = "pkg_01HXX1234567890ABCDEFGHIJL"
COMPANION_ID = "usr_01HXX1234567890ABCDEFGHIJM"
TPL_V1 = "v1.0.0"
SCHEDULED_AT = datetime(2026, 6, 15, 10, 30, tzinfo=timezone.utc)


def _set_salt(monkeypatch, *, primary: str, version: int, legacy: str = "") -> None:
    """切换 salt 环境 (PRIMARY 优先, legacy fallback)。"""
    monkeypatch.setattr(
        contract_hash.settings, "contract_pseudonym_salt_primary", primary
    )
    monkeypatch.setattr(
        contract_hash.settings, "contract_pseudonym_salt", legacy
    )
    monkeypatch.setattr(
        contract_hash.settings, "contract_pseudonym_salt_version", version
    )


class TestSaltRotationDrillPlanD:
    def test_full_rotation_drill(self, monkeypatch):
        # ───── ① 存量合同: OLD salt, salt_version=1 ─────
        _set_salt(monkeypatch, primary=OLD_SALT, version=1)
        existing_version = contract_hash.settings.contract_pseudonym_salt_version
        assert existing_version == 1

        existing = generate_contract_hash_at_commit_time(
            order_id=ORDER_ID_EXISTING,
            amount_cny=29900,
            service_package_id=SERVICE_PKG_ID,
            scheduled_at=SCHEDULED_AT,
            patient_name=PATIENT_NAME,
            patient_id_card_last4=ID_CARD_LAST4,
            companion_id=COMPANION_ID,
            template_version=TPL_V1,
        )
        # 冻结存量: snapshot + contract_hash (模拟写入 service_contracts)
        existing_snapshot = dict(existing.hash_inputs_snapshot)
        existing_contract_hash = existing.contract_hash
        existing_pseudonym_hash = existing_snapshot["patient_pseudonym_hash"]

        # 验证存量 pseudonym_hash 确实用 OLD salt 算的
        assert existing_pseudonym_hash == compute_patient_pseudonym_hash(
            patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4
        )

        # ───── ② 轮换: 切 PRIMARY 为 NEW salt + version 递增到 2 ─────
        _set_salt(monkeypatch, primary=NEW_SALT, version=2)
        new_version = contract_hash.settings.contract_pseudonym_salt_version

        # ───── ③ 新合同: 同患者同 last4, 用 NEW salt ─────
        new_contract = generate_contract_hash_at_commit_time(
            order_id=ORDER_ID_NEW,
            amount_cny=29900,
            service_package_id=SERVICE_PKG_ID,
            scheduled_at=SCHEDULED_AT,
            patient_name=PATIENT_NAME,
            patient_id_card_last4=ID_CARD_LAST4,
            companion_id=COMPANION_ID,
            template_version=TPL_V1,
        )
        new_pseudonym_hash = new_contract.hash_inputs_snapshot[
            "patient_pseudonym_hash"
        ]

        # ───── ④ 断言 ─────

        # (a) 新合同 pseudonym_hash 用新 salt → 与 OLD salt 算的不同 (轮换生效)
        assert new_pseudonym_hash != existing_pseudonym_hash, (
            "轮换后新合同 pseudonym_hash 必须与 OLD salt 算的不同"
        )
        # 验证新 hash 确实是 NEW salt 算出来的
        assert new_pseudonym_hash == compute_patient_pseudonym_hash(
            patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4
        )

        # (b) salt_version 递增 (1 → 2)
        assert new_version == existing_version + 1 == 2

        # (c) 存量合同 recompute 仍 pass (snapshot 冻结值, 不受轮换影响)
        #     —— 这是方案 D 的命脉: recompute 用存好的 snapshot, 不重算 pseudonym_hash
        recomputed = recompute_contract_hash(
            hash_inputs_snapshot=existing_snapshot,
            template_version=existing_snapshot["template_version"],
        )
        assert recomputed == existing_contract_hash, (
            "存量合同 recompute 必须 pass —— snapshot 冻结值不受 salt 轮换影响"
        )

        # (d) 存量 contract_hash 零变化 (WORM 保持)
        #     即使当前 salt 已换成 NEW, 存量的 snapshot 仍含 OLD pseudonym_hash,
        #     recompute 结果恒等于冻结的 contract_hash
        assert existing_snapshot["patient_pseudonym_hash"] == existing_pseudonym_hash
        assert recomputed == existing_contract_hash

    def test_existing_recompute_immune_to_salt_change(self, monkeypatch):
        """单独验证: 存量 recompute 完全不读当前 salt (snapshot 自洽)。"""
        # 用 OLD salt 造存量
        _set_salt(monkeypatch, primary=OLD_SALT, version=1)
        existing = generate_contract_hash_at_commit_time(
            order_id=ORDER_ID_EXISTING,
            amount_cny=29900,
            service_package_id=SERVICE_PKG_ID,
            scheduled_at=SCHEDULED_AT,
            patient_name=PATIENT_NAME,
            patient_id_card_last4=ID_CARD_LAST4,
            companion_id=COMPANION_ID,
            template_version=TPL_V1,
        )
        snapshot = dict(existing.hash_inputs_snapshot)
        frozen_hash = existing.contract_hash

        # 切 salt 三次, 每次 recompute 都必须等于冻结值
        for primary, ver in [(NEW_SALT, 2), ("yet-another-salt-v3", 3), ("", 1)]:
            if primary:
                _set_salt(monkeypatch, primary=primary, version=ver)
            else:
                # 极端: 当前 salt 全空 (recompute 不该 care, 因为不重算 pseudonym)
                _set_salt(monkeypatch, primary="", version=ver, legacy="")
            recomputed = recompute_contract_hash(
                hash_inputs_snapshot=snapshot,
                template_version=snapshot["template_version"],
            )
            assert recomputed == frozen_hash

    def test_primary_fallback_to_legacy(self, monkeypatch):
        """向后兼容: PRIMARY 空时 fallback legacy CONTRACT_PSEUDONYM_SALT。"""
        # 只设 legacy, PRIMARY 空
        _set_salt(monkeypatch, primary="", version=1, legacy=OLD_SALT)
        h_legacy = compute_patient_pseudonym_hash(
            patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4
        )
        # 设 PRIMARY = 同值, 应得相同 hash (证明 fallback 等价)
        _set_salt(monkeypatch, primary=OLD_SALT, version=1, legacy="")
        h_primary = compute_patient_pseudonym_hash(
            patient_name=PATIENT_NAME, id_card_last4=ID_CARD_LAST4
        )
        assert h_legacy == h_primary
