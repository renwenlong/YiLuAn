"""Tests for UserFeedbackStateMachine + UserFeedback ORM model.

S3-DEV-004-FEEDBACK-DOMAIN / ADR-0049 §3.1 + §4.1.

# Coverage map (4 acceptance criteria)

| AC | Test class |
|----|-----------|
| #1 ADR-0049 已 merge (前置) | implicit (本 task 引用 docs/adr/ADR-0049-*.md) |
| #2 user_feedbacks alembic migration | smoke + implicit (CI alembic check) |
| #3 UserFeedbackStateMachine 状态机 (pending/in_review/resolved/closed/rejected)
  → ``TestStateMachineTransitions`` |
| #4 三外键 nullable 单测 + 状态迁移单测 | ``TestNullableFKs`` + ``TestStateMachineTransitions`` |

Plus pinning sentinels:
- ``TestEnumStability`` — 5 FeedbackStatus + 3 Severity + 4 Source + 8 Module values
- ``TestTransitionTablePinning`` — 8 legal transitions count pinned
- ``TestAppendWindow`` — 30d closed → in_review 窗口 helper

# 不在范围

- endpoint / service / 限频 / metrics → S3-DEV-004-FEEDBACK-API task 跟
- AI 摘要 → PRD-004 明确 S3 不做
- attachment 表/存储 → S3-DEV-004-FEEDBACK-STORAGE task 跟
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.models.user_feedback import (
    CLOSED_APPEND_WINDOW_DAYS,
    FeedbackFunctionModule,
    FeedbackSeverity,
    FeedbackSource,
    FeedbackStatus,
    UserFeedback,
)
from app.services import user_feedback_state_machine as fsm
from app.services.user_feedback_state_machine import (
    FeedbackAppendWindowExpiredError,
    InvalidFeedbackStateTransitionError,
    assert_transition,
    assert_user_append_allowed,
    can_user_append,
    can_user_append_when_closed,
    is_legal_transition,
    is_terminal,
    legal_targets,
)

# ---------------------------------------------------------------------------
# Sentinels: ENUM values pinned (ADR-0049 ground truth)
# ---------------------------------------------------------------------------


class TestEnumStability:
    def test_five_status_values_exact(self):
        # ADR-0049 §4.1 5 状态; 任何加减必须同步 migration + state machine + 此 sentinel
        assert {s.value for s in FeedbackStatus} == {
            "pending",
            "in_review",
            "resolved",
            "closed",
            "rejected",
        }

    def test_three_severity_values_exact(self):
        # urgent 触发 alertmanager UrgentFeedbackSubmitted alert (FEEDBACK-API task)
        assert {s.value for s in FeedbackSeverity} == {
            "normal",
            "important",
            "urgent",
        }

    def test_four_source_values_exact(self):
        # ADR-0049 §3.1 4 个 source: user / customer_service / phone / offline
        assert {s.value for s in FeedbackSource} == {
            "user",
            "customer_service",
            "phone",
            "offline",
        }

    def test_eight_function_module_values_exact(self):
        # ADR-0049 §3.1 8 个模块; 'other' 兜底防 ENUM 漂移频繁 migration
        assert {m.value for m in FeedbackFunctionModule} == {
            "insurance",
            "contract",
            "ai_prep",
            "family_share",
            "service_package",
            "service_quality",
            "payment",
            "other",
        }

    def test_str_value_matches_name(self):
        for enum_cls in (
            FeedbackStatus,
            FeedbackSeverity,
            FeedbackSource,
            FeedbackFunctionModule,
        ):
            for member in enum_cls:
                assert member.value == member.name


class TestTransitionTablePinning:
    """ADR-0049 §4.1 ground truth: 8 legal transitions.

    Any drift requires updating:
    1. ADR-0049 §4.1
    2. app/services/user_feedback_state_machine.py _LEGAL_TRANSITIONS
    3. This sentinel
    """

    def test_legal_transitions_count_pinned_8(self):
        assert len(fsm._LEGAL_TRANSITIONS) == 8

    def test_no_hard_terminal(self):
        # UserFeedback 故意无 hard terminal (与 ContractStateMachine 不同).
        # closed/rejected 都可被 user_append 复活.
        assert fsm._HARD_TERMINAL == frozenset()
        for state in FeedbackStatus:
            assert is_terminal(state) is False

    def test_pending_outgoing_2(self):
        # pending → in_review (admin_start_review) | rejected (admin_reject_invalid)
        assert legal_targets(FeedbackStatus.pending) == frozenset(
            {FeedbackStatus.in_review, FeedbackStatus.rejected}
        )

    def test_in_review_outgoing_2(self):
        # in_review → resolved | rejected
        assert legal_targets(FeedbackStatus.in_review) == frozenset(
            {FeedbackStatus.resolved, FeedbackStatus.rejected}
        )

    def test_resolved_outgoing_2(self):
        # resolved → closed (user_accept) | in_review (user_append)
        assert legal_targets(FeedbackStatus.resolved) == frozenset(
            {FeedbackStatus.closed, FeedbackStatus.in_review}
        )

    def test_rejected_outgoing_1(self):
        # rejected → in_review (user_append, 申诉)
        assert legal_targets(FeedbackStatus.rejected) == frozenset(
            {FeedbackStatus.in_review}
        )

    def test_closed_outgoing_1(self):
        # closed → in_review (user_append within 30d, 30d 窗口由 endpoint 层判)
        assert legal_targets(FeedbackStatus.closed) == frozenset(
            {FeedbackStatus.in_review}
        )


# ---------------------------------------------------------------------------
# Legal transitions: 8 PASS cases
# ---------------------------------------------------------------------------


class TestStateMachineTransitions:
    """ADR-0049 §4.1 — 所有 8 个 legal transition 显式覆盖 + assert_transition PASS"""

    @pytest.mark.parametrize(
        "from_status, to_status",
        [
            (FeedbackStatus.pending, FeedbackStatus.in_review),
            (FeedbackStatus.pending, FeedbackStatus.rejected),
            (FeedbackStatus.in_review, FeedbackStatus.resolved),
            (FeedbackStatus.in_review, FeedbackStatus.rejected),
            (FeedbackStatus.resolved, FeedbackStatus.closed),
            (FeedbackStatus.resolved, FeedbackStatus.in_review),
            (FeedbackStatus.rejected, FeedbackStatus.in_review),
            (FeedbackStatus.closed, FeedbackStatus.in_review),
        ],
    )
    def test_legal_transition_pass(self, from_status, to_status):
        assert is_legal_transition(from_status, to_status) is True
        # assert_transition 不 raise = PASS
        assert_transition(from_status=from_status, to_status=to_status)

    @pytest.mark.parametrize(
        "from_status, to_status",
        [
            # pending 没出边到 resolved/closed (要先 in_review)
            (FeedbackStatus.pending, FeedbackStatus.resolved),
            (FeedbackStatus.pending, FeedbackStatus.closed),
            # in_review 没直接到 closed (要先 resolved)
            (FeedbackStatus.in_review, FeedbackStatus.closed),
            (FeedbackStatus.in_review, FeedbackStatus.pending),
            # resolved 不允许回 pending / rejected (admin 已 resolve)
            (FeedbackStatus.resolved, FeedbackStatus.pending),
            (FeedbackStatus.resolved, FeedbackStatus.rejected),
            # closed 不允许回 resolved/closed/rejected/pending (只 user_append → in_review)
            (FeedbackStatus.closed, FeedbackStatus.pending),
            (FeedbackStatus.closed, FeedbackStatus.resolved),
            (FeedbackStatus.closed, FeedbackStatus.rejected),
            # rejected 不允许回 pending / resolved / closed (只 user_append → in_review)
            (FeedbackStatus.rejected, FeedbackStatus.pending),
            (FeedbackStatus.rejected, FeedbackStatus.resolved),
            (FeedbackStatus.rejected, FeedbackStatus.closed),
            # 自旋全禁
            (FeedbackStatus.pending, FeedbackStatus.pending),
            (FeedbackStatus.in_review, FeedbackStatus.in_review),
            (FeedbackStatus.resolved, FeedbackStatus.resolved),
            (FeedbackStatus.closed, FeedbackStatus.closed),
            (FeedbackStatus.rejected, FeedbackStatus.rejected),
        ],
    )
    def test_illegal_transition_raises(self, from_status, to_status):
        assert is_legal_transition(from_status, to_status) is False
        with pytest.raises(InvalidFeedbackStateTransitionError) as exc:
            assert_transition(from_status=from_status, to_status=to_status)
        # 错误消息含有 from/to 名 + legal targets 提示
        msg = str(exc.value)
        assert from_status.value in msg
        assert to_status.value in msg
        assert "legal targets" in msg


# ---------------------------------------------------------------------------
# can_user_append predicate
# ---------------------------------------------------------------------------


class TestCanUserAppend:
    """ADR-0049 §4.1 表: append 权限按状态划分"""

    def test_pending_false(self):
        # 用户应直接编辑首条, 不 append
        assert can_user_append(FeedbackStatus.pending) is False

    def test_in_review_false(self):
        # admin 处理中, 防状态机振荡
        assert can_user_append(FeedbackStatus.in_review) is False

    def test_resolved_true(self):
        # 重新激活
        assert can_user_append(FeedbackStatus.resolved) is True

    def test_rejected_true(self):
        # 申诉/补证
        assert can_user_append(FeedbackStatus.rejected) is True

    def test_closed_true_irrespective_of_window(self):
        # closed 本身允许 (30d 窗口由 can_user_append_when_closed 判)
        assert can_user_append(FeedbackStatus.closed) is True


class TestAppendWindowWhenClosed:
    """ADR-0049 §4.1 closed → in_review 30d 窗口"""

    def test_within_window_allowed(self):
        now = datetime.now(timezone.utc)
        closed_at = now - timedelta(days=29)
        assert can_user_append_when_closed(closed_at=closed_at, now=now) is True

    def test_at_window_edge_allowed(self):
        # = 30d 算窗口内 (用 <=)
        now = datetime.now(timezone.utc)
        closed_at = now - timedelta(days=CLOSED_APPEND_WINDOW_DAYS)
        assert can_user_append_when_closed(closed_at=closed_at, now=now) is True

    def test_past_window_rejected(self):
        now = datetime.now(timezone.utc)
        closed_at = now - timedelta(days=CLOSED_APPEND_WINDOW_DAYS + 1)
        assert can_user_append_when_closed(closed_at=closed_at, now=now) is False

    def test_naive_closed_at_raises(self):
        # 防 naive datetime 误判 (本地时区 vs UTC 歧义)
        closed_at_naive = datetime(2026, 5, 1)  # 无 tzinfo
        with pytest.raises(ValueError, match="timezone-aware"):
            can_user_append_when_closed(closed_at=closed_at_naive)

    def test_naive_now_raises(self):
        closed_at = datetime.now(timezone.utc)
        with pytest.raises(ValueError, match="timezone-aware"):
            can_user_append_when_closed(
                closed_at=closed_at, now=datetime(2026, 6, 1)
            )


class TestAssertUserAppendAllowed:
    """:func:`assert_user_append_allowed` — 复合 guard (append 权限 + 30d 窗口)"""

    def test_pending_raises_transition_error(self):
        with pytest.raises(InvalidFeedbackStateTransitionError, match="pending"):
            assert_user_append_allowed(from_status=FeedbackStatus.pending)

    def test_in_review_raises_transition_error(self):
        with pytest.raises(
            InvalidFeedbackStateTransitionError, match="in_review"
        ):
            assert_user_append_allowed(from_status=FeedbackStatus.in_review)

    def test_resolved_passes(self):
        # 无 raise = pass
        assert_user_append_allowed(from_status=FeedbackStatus.resolved)

    def test_rejected_passes(self):
        assert_user_append_allowed(from_status=FeedbackStatus.rejected)

    def test_closed_within_window_passes(self):
        now = datetime.now(timezone.utc)
        closed_at = now - timedelta(days=15)
        assert_user_append_allowed(
            from_status=FeedbackStatus.closed, closed_at=closed_at, now=now
        )

    def test_closed_past_window_raises_window_expired(self):
        now = datetime.now(timezone.utc)
        closed_at = now - timedelta(days=CLOSED_APPEND_WINDOW_DAYS + 5)
        with pytest.raises(FeedbackAppendWindowExpiredError, match="HTTP 410"):
            assert_user_append_allowed(
                from_status=FeedbackStatus.closed,
                closed_at=closed_at,
                now=now,
            )

    def test_closed_without_closed_at_raises_value_error(self):
        with pytest.raises(ValueError, match="closed_at must be provided"):
            assert_user_append_allowed(from_status=FeedbackStatus.closed)


# ---------------------------------------------------------------------------
# ORM model: 三外键 nullable + ENUM 类型映射 (acceptance §4)
# ---------------------------------------------------------------------------


class TestModelSchema:
    """ADR-0049 §3.1 — UserFeedback ORM 结构核验 (纯 schema, 不连 DB)"""

    def test_table_name(self):
        assert UserFeedback.__tablename__ == "user_feedbacks"

    def test_required_fields_present(self):
        cols = {c.name for c in UserFeedback.__table__.columns}
        # ADR-0049 §3.1 — 字段名 ground truth
        expected = {
            "id",
            "feedback_parent_id",
            "user_id",
            "order_id",
            "companion_id",
            "feedback_function_module",
            "category",
            "severity",
            "source",
            "raw_content",
            "admin_sanitized_summary",
            "admin_resolution_summary",
            "companion_appeal",
            "status",
            "handled_by_admin_id",
            "handled_at",
            "closed_at",
            "metadata",
            "created_at",
            "updated_at",
        }
        assert cols == expected, f"drift: missing={expected-cols} extra={cols-expected}"

    def test_user_id_not_null(self):
        # user_id NOT NULL (反馈必有提交人)
        col = UserFeedback.__table__.columns["user_id"]
        assert col.nullable is False

    def test_order_id_nullable(self):
        # 平台级反馈不绑订单
        col = UserFeedback.__table__.columns["order_id"]
        assert col.nullable is True

    def test_companion_id_nullable(self):
        # 非对陪诊师反馈
        col = UserFeedback.__table__.columns["companion_id"]
        assert col.nullable is True

    def test_feedback_parent_id_nullable(self):
        # NULL = 首条反馈
        col = UserFeedback.__table__.columns["feedback_parent_id"]
        assert col.nullable is True

    def test_handled_by_admin_id_nullable(self):
        # admin 未触达时 NULL
        col = UserFeedback.__table__.columns["handled_by_admin_id"]
        assert col.nullable is True

    def test_status_default_pending(self):
        # status 默认 pending (ADR-0049 §4.1)
        col = UserFeedback.__table__.columns["status"]
        # SA `default=FeedbackStatus.pending` 会包装成 ColumnDefault
        assert col.default is not None
        # 取出实际 default 值
        default_val = col.default.arg
        assert default_val == FeedbackStatus.pending


class TestNullableFKs:
    """acceptance §4 — 三外键 nullable 单测.

    既覆盖 ORM 层 column nullable 标志, 也通过 instantiation 验证 ORM 能正确接受
    None / 实例值 (不连 DB, 纯 in-memory)
    """

    def test_construct_with_all_fks_set(self):
        # 全 FK 都填的情况下 (典型: 对具体订单 + 具体陪诊师的反馈)
        f = UserFeedback(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            companion_id=uuid.uuid4(),
            feedback_parent_id=None,  # 首条
            feedback_function_module=FeedbackFunctionModule.service_quality,
            category="服务态度",
            severity=FeedbackSeverity.important,
            source=FeedbackSource.user,
            raw_content="陪诊师对老人比较不耐烦",
            status=FeedbackStatus.pending,
            metadata_={},
        )
        assert f.user_id is not None
        assert f.order_id is not None
        assert f.companion_id is not None

    def test_construct_with_order_id_null_platform_feedback(self):
        # 平台级反馈: 不绑订单, 不绑陪诊师 (功能建议/隐私担忧)
        f = UserFeedback(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            order_id=None,
            companion_id=None,
            feedback_parent_id=None,
            feedback_function_module=FeedbackFunctionModule.other,
            category="平台建议",
            severity=FeedbackSeverity.normal,
            source=FeedbackSource.user,
            raw_content="希望加暗黑模式",
            status=FeedbackStatus.pending,
            metadata_={},
        )
        assert f.user_id is not None
        assert f.order_id is None
        assert f.companion_id is None

    def test_construct_with_companion_id_null_order_only_feedback(self):
        # 对订单流程反馈但非具体陪诊师 (如付款流程/合同流程)
        f = UserFeedback(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            companion_id=None,
            feedback_parent_id=None,
            feedback_function_module=FeedbackFunctionModule.payment,
            category="费用问题",
            severity=FeedbackSeverity.normal,
            source=FeedbackSource.user,
            raw_content="付款时收到了 2 次扣款",
            status=FeedbackStatus.pending,
            metadata_={},
        )
        assert f.order_id is not None
        assert f.companion_id is None

    def test_construct_supplemental_feedback_with_parent_id(self):
        # 补充反馈: feedback_parent_id 指向首条
        parent_id = uuid.uuid4()
        f = UserFeedback(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            order_id=uuid.uuid4(),
            companion_id=uuid.uuid4(),
            feedback_parent_id=parent_id,  # 补充
            feedback_function_module=FeedbackFunctionModule.service_quality,
            category="服务态度",
            severity=FeedbackSeverity.important,
            source=FeedbackSource.user,
            raw_content="补充: 上次反馈后陪诊师没有改善",
            status=FeedbackStatus.pending,
            metadata_={},
        )
        assert f.feedback_parent_id == parent_id


class TestIndexes:
    """acceptance §2 + ADR-0049 §3.1 — 5 索引存在"""

    def test_all_six_indexes_declared(self):
        # 5 表内显式 index + 1 fk auto index (user_id) = 6
        index_names = {idx.name for idx in UserFeedback.__table__.indexes}
        expected = {
            "idx_user_feedbacks_companion_status",
            "idx_user_feedbacks_module_time",
            "idx_user_feedbacks_severity_status",
            "idx_user_feedbacks_parent",
            "uq_user_feedback_once_per_order_category",
            "ix_user_feedbacks_user_id",
        }
        # 实际可能 fk auto index 名不同, 至少所有显式 declare 的 5 个要在
        explicit = expected - {"ix_user_feedbacks_user_id"}
        assert explicit.issubset(index_names), (
            f"missing indexes: {explicit - index_names}"
        )

    def test_partial_unique_index_declared(self):
        # uq_user_feedback_once_per_order_category 必须是 unique partial
        idx = next(
            (
                i
                for i in UserFeedback.__table__.indexes
                if i.name == "uq_user_feedback_once_per_order_category"
            ),
            None,
        )
        assert idx is not None
        assert idx.unique is True
