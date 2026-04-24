# Alembic Migration Reversibility Report

- Generated: 2026-04-24 19:37:10
- Source: `backend/alembic/versions/`
- Tool: `backend/scripts/check_migration_reversibility.py`
- 关联 ADR: [`ADR-0028`](decisions/ADR-0028-canary-release-and-rollback.md) §4.5

## Summary

- Total revisions: **19**
- ✅ Reversible:    **16**
- ⚠️  Manual:        **1** (人工 review)
- ❌ Irreversible:  **2** (downgrade 缺失/raise/pass)

## 评级标准

- **reversible**: `downgrade()` 内含 `op.*` DDL 调用, 且无人工标记。
- **manual**: `downgrade()` 含 `op.*` 但带有 `drop value` / `backfill` / `manual` 等标记;
  或 body 非空但完全没有 `op.*` 调用。需要 DBA + 架构师人工 review 后确认是否可回滚。
- **irreversible**: `downgrade()` 缺失、为 `pass`、或 `raise NotImplementedError`。
  在 ADR-0028 灰度发布场景下, 该 revision **不允许**通过 alembic downgrade 回滚, 必须走
  前向修复 + 数据补偿 (见 `docs/RUNBOOK_ROLLBACK.md` 场景 C)。

## Per-revision detail

| File | Revision | Down | Class | Lines | Reason |
|---|---|---|---|---:|---|
| `12e9862becff_add_service_hospitals_column_to_.py` | `12e9862becff` | `f3a7b8c9d0e1` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `2efb4290575a_add_service_types_to_companion_profile.py` | `2efb4290575a` | `a1b2c3d4e5f6` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `6bf94c0a3831_add_expires_at_to_payment_callback_log_.py` | `6bf94c0a3831` | `d9e0f1a2b3c4` | ✅ reversible | 2 | downgrade() contains op.* DDL calls |
| `a1b2c3d4e5f6_add_roles_field.py` | `a1b2c3d4e5f6` | `bbd5bf5de583` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `a50c6c117291_merge_heads.py` | `a50c6c117291` | `?` | ❌ irreversible | 1 | downgrade() is just `pass` |
| `a7b8c9d0e1f2_add_deleted_at_to_users.py` | `a7b8c9d0e1f2` | `f4a5b6c7d8e9` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `a8b9c0d1e2f3_add_message_indexes.py` | `a8b9c0d1e2f3` | `f1a2b3c4d5e6` | ✅ reversible | 5 | downgrade() contains op.* DDL calls |
| `b4c5d6e7f8a9_add_familiar_hospitals_to_companion.py` | `b4c5d6e7f8a9` | `f3a7b8c9d0e1` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `b7c8d9e0f1a2_align_payments_columns_and_verify_enums.py` | `b7c8d9e0f1a2` | `a50c6c117291` | ⚠️ manual | 5 | downgrade() has op.* AND manual markers (review needed): ['drop value'] |
| `bbd5bf5de583_initial.py` | `bbd5bf5de583` | `?` | ✅ reversible | 26 | downgrade() contains op.* DDL calls |
| `c5d6e7f8a9b0_rename_familiar_hospitals_to_service.py` | `c5d6e7f8a9b0` | `b4c5d6e7f8a9` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `c8d9e0f1a2b3_add_payment_callback_log.py` | `c8d9e0f1a2b3` | `b7c8d9e0f1a2` | ✅ reversible | 4 | downgrade() contains op.* DDL calls |
| `d1e2f3a4b5c6_add_sms_send_log.py` | `d1e2f3a4b5c6` | `6bf94c0a3831` | ✅ reversible | 5 | downgrade() contains op.* DDL calls |
| `d6e7f8a9b0c1_add_payment_unique_constraint.py` | `d6e7f8a9b0c1` | `c5d6e7f8a9b0` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `d9e0f1a2b3c4_add_admin_audit_logs.py` | `d9e0f1a2b3c4` | `c8d9e0f1a2b3` | ✅ reversible | 2 | downgrade() contains op.* DDL calls |
| `e3f4a5b6c7d8_add_service_city_to_companion_profiles.py` | `e3f4a5b6c7d8` | `12e9862becff` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `f1a2b3c4d5e6_add_expires_at_and_new_order_statuses.py` | `f1a2b3c4d5e6` | `12e9862becff` | ✅ reversible | 1 | downgrade() contains op.* DDL calls |
| `f3a7b8c9d0e1_add_hospital_region_tags.py` | `f3a7b8c9d0e1` | `2efb4290575a` | ✅ reversible | 6 | downgrade() contains op.* DDL calls |
| `f4a5b6c7d8e9_add_start_service_request_notification.py` | `f4a5b6c7d8e9` | `e3f4a5b6c7d8` | ❌ irreversible | 1 | downgrade() is just `pass` |

## Action items

- ❌ 2 个 irreversible revision: 在 ADR-0028 §4.5 
  Expand-Contract 框架下, 任何 irreversible revision 都应被视为 *破坏性变更*, 
  必须放在独立的 contract 阶段单独发布, **绝不能与 expand 合并**。
- ⚠️  1 个 manual revision: 在 `docs/RUNBOOK_ROLLBACK.md` 场景 C 
  执行前必须由 DBA + 架构师双签确认。

## CI integration (TODO, W18)

```yaml
- name: Migration reversibility audit
  run: python backend/scripts/check_migration_reversibility.py
  # 后续可加: 若 irreversible count 较 baseline 增加 -> fail
```
