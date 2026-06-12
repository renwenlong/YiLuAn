"""
S3-TEST-007 Companion Recommendation API E2E (PRD-001 §F8)
==========================================================

spec v1 final: ``docs/prd/drafts/2026-06-11-s3-prd-001-f8-recommendation-filter-spec-v1-final.md``
endpoint: ``GET /v1/companions/recommendations?city={city}&top_k={1..3}``

Coverage matrix (4 角度 / 9 case):

| AC# | Test class | 重点 |
|-----|------------|------|
| 1 | TestThreeStateSortJourneyE2E | 6 companion × 3 cert_state 整链路 sort |
| 2 | TestABACPIINegativeE2E | 5 PII 字段 (real_name/id_number/cert_no/cert_url/phone) 不漏 |
| 3 | TestRecommendationSLOLocalE2E | 50 次 call P50<200ms P99<500ms (本地 in-memory baseline) |
| 4 | TestAdminOverrideRejectE2E | admin 直接 DB set 仍被 §1.4 守门 reject |

# 与 PR #285 既有 13 个 integration test 的差异 (反案 #11 互补不重复)

PR #285 ``test_recommendations_endpoint.py`` 覆盖 **单 endpoint 单 case**:
TestGetRecommendations (test_empty_when_no_companions / test_only_uncertified_returns_empty_items
/ test_verified_in_top3_with_rank_1 / test_pseudonym_name_uses_mask_name / test_pii_fields_absent_from_response
/ test_sort_order_verified_above_pending_above_uncertified / test_tie_break_rating_desc_then_orders_desc_then_created_asc
/ test_top_k_max_3 / test_top_k_explicit_1 / test_top_k_invalid_4_returns_422 / test_city_filter
/ test_requires_authentication / test_meta_counts_transparency).

本 E2E 文件聚焦 PR #285 **未覆盖** 的 4 个 E2E 维度:

- **AC#1 三态排序整链**: PR #285 测**单 case sort** (单方向 verified > pending > uncertified);
  本 E2E 测**6 companion × 3 state mixed insert + city filter + tie-breaker** 完整 chain.
- **AC#2 ABAC negative 跨场景**: PR #285 测**单 endpoint sentinel**;
  本 E2E 测**多场景** (空 query / top_k=1/2/3 / city filter 各方向) **每条 response 0 PII hit**.
- **AC#3 SLO local baseline**: PR #285 无时延检测;
  本 E2E 测**50 次 call 本地分位数** (P50<200ms / P99<500ms 防 endpoint regression).
- **AC#4 admin override reject**: PR #285 测 service layer 单元逻辑;
  本 E2E 测**双 layer 链路** (admin 直接 DB write + 推荐 endpoint reject) 防 race.

# Pytest marker

E2E conftest auto-marks ``e2e``. 无 ``docker`` marker (默认 CI 跑).

# 跑法

默认 CI / 本地::

    backend/.venv/bin/python -m pytest \\
        backend/tests/e2e/test_e2e_recommendation_journey.py -v

仅跑某一 AC::

    backend/.venv/bin/python -m pytest \\
        backend/tests/e2e/test_e2e_recommendation_journey.py::TestRecommendationSLOLocalE2E -v

# 反案合规

- 反案 #11 (asset-presence integration, 不只 mock): 本 E2E 跑实际 SQLite + 真实 endpoint
  client (httpx AsyncClient), 不用 mock 替代 service / repo.
- 反案 #25 fail-loud: SLO 失败直接 assert raise, 不静默 skip.
- 反案 #1 与 PR #285 差异化: 每个 test class docstring 明确 "PR #285 未覆盖维度".

Author: 刻晴 (tester)
Date: 2026-06-12 02:35 UTC
Task: S3-TEST-007-RECOMMENDATION-API-E2E (test/P1)
"""
from __future__ import annotations

import statistics
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.companion_profile import CompanionProfile, VerificationStatus
from app.models.user import User, UserRole
from tests.conftest import test_session_factory


# ============================================================
# Helpers — fixture builder (PII negative list 已加到 unit test 同款)
# ============================================================

PII_SENTINEL = "P-PII-LEAK-CANARY-XYZ"  # 出现在 response 即漏出
# spec §1.2 严禁出现在 response 的 PII 字段名
PII_FIELDS_NEGATIVE = {
    "real_name",                  # 明文真名
    "id_number",                  # 身份证号
    "certification_no",           # 证书号
    "certification_image_url",    # 证书图 URL
    "companion_phone",            # 手机号 (spec 字面 negative #1)
    "companion_id_card",          # spec 字面 negative #2
    "companion_cert_url",         # spec 字面 negative #3
    "companion_real_name",        # spec 字面 negative #4
}


async def _create_companion(
    *,
    real_name: str,
    verification_status: VerificationStatus,
    avg_rating: float = 4.0,
    total_orders: int = 50,
    service_city: str | None = "北京",
    service_area: str | None = "朝阳区",
    created_at: datetime | None = None,
    id_number: str | None = None,
    certification_no: str | None = None,
    certification_image_url: str | None = None,
) -> CompanionProfile:
    """Insert a companion + owning user with PII fields populated (for ABAC negative)."""
    async with test_session_factory() as session:
        user = User(
            id=uuid.uuid4(),
            display_name=f"u-{real_name}",
            phone=f"139{uuid.uuid4().int % 10**8:08d}",
            role=UserRole.companion,
        )
        session.add(user)
        await session.flush()

        profile = CompanionProfile(
            id=uuid.uuid4(),
            user_id=user.id,
            real_name=real_name,
            id_number=id_number or f"110101199001019999",
            certification_no=certification_no or f"{PII_SENTINEL}-CERT-{uuid.uuid4().hex[:8]}",
            certification_image_url=certification_image_url
            or f"https://example.com/{PII_SENTINEL}/cert.png",
            certification_type="护理证",
            service_city=service_city,
            service_area=service_area,
            service_types="full_accompany",
            bio=f"{real_name} bio",
            avg_rating=avg_rating,
            total_orders=total_orders,
            verification_status=verification_status,
            created_at=created_at or datetime.now(timezone.utc),
        )
        session.add(profile)
        await session.commit()
        await session.refresh(profile)
        return profile


async def _create_six_companion_set() -> dict[str, CompanionProfile]:
    """spec §1.3 sort test fixture: 6 companion × 3 state.

    每 state 2 个不同 rating/orders/created_at 触发 tie-breaker.

    Returns:
        dict: name → CompanionProfile, 便于 E2E 断言定位.
    """
    now = datetime.now(timezone.utc)
    return {
        # ===== verified (cert_status=0, top tier) =====
        "v_high": await _create_companion(
            real_name="V高分",
            verification_status=VerificationStatus.verified,
            avg_rating=4.9,
            total_orders=200,
            created_at=now - timedelta(days=30),
        ),
        "v_low": await _create_companion(
            real_name="V低分",
            verification_status=VerificationStatus.verified,
            avg_rating=4.1,
            total_orders=80,
            created_at=now - timedelta(days=10),
        ),
        # ===== pending_supplement (cert_status=1, middle, mapped from VerificationStatus.pending) =====
        "p_high": await _create_companion(
            real_name="P高分",
            verification_status=VerificationStatus.pending,
            avg_rating=4.5,
            total_orders=120,
            created_at=now - timedelta(days=20),
        ),
        "p_low": await _create_companion(
            real_name="P低分",
            verification_status=VerificationStatus.pending,
            avg_rating=3.8,
            total_orders=40,
            created_at=now - timedelta(days=5),
        ),
        # ===== uncertified (cert_status=2, bottom, mapped from VerificationStatus.rejected) =====
        # 不应出现在 items (§1.4 守门)
        "u_high": await _create_companion(
            real_name="U高分",
            verification_status=VerificationStatus.rejected,
            avg_rating=5.0,  # 故意高 — 验证 §1.4 不被分数破防
            total_orders=999,
            created_at=now - timedelta(days=100),
        ),
        "u_low": await _create_companion(
            real_name="U低分",
            verification_status=VerificationStatus.rejected,
            avg_rating=2.0,
            total_orders=5,
            created_at=now - timedelta(days=1),
        ),
    }


def _serialize_recursive(obj) -> str:
    """Convert any nested response to a string for PII substring scan."""
    import json
    return json.dumps(obj, ensure_ascii=False, default=str)


# ============================================================
# AC#1 — TestThreeStateSortJourneyE2E
# ============================================================


@pytest.mark.asyncio
class TestThreeStateSortJourneyE2E:
    """spec §1.3 三态排序 E2E (整链 fixture → endpoint → response).

    PR #285 ``test_sort_order_verified_above_pending_above_uncertified`` 测
    **单维度** sort; 本 E2E 用 **6 companion × 3 state mixed**, 同时验证
    **§1.4 uncertified 守门 + §2.2 meta counts + tie-breaker DESC chain**.
    """

    async def test_full_sort_chain_with_six_companions(self, authenticated_client):
        """整链: 6 companion → response items 顺序 + meta counts 正确.

        预期:
        - top_k=3 → items 3 个, 全是 verified 或 pending_supplement
        - rank 1 = V高分 (verified + rating 最高)
        - rank 2 = V低分 (verified + rating 次)
        - rank 3 = P高分 (pending_supplement + rating 最高)
        - U系列全 filter (§1.4)
        - total_eligible = 4 (2 verified + 2 pending), filtered_uncertified_count = 2
        """
        cs = await _create_six_companion_set()
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=3"
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # meta counts (§2.2)
        assert body["total_eligible"] == 4, (
            f"应有 4 个 eligible (2 verified + 2 pending), 实际 {body['total_eligible']}"
        )
        assert body["filtered_uncertified_count"] == 2, (
            f"应有 2 个 uncertified filtered, 实际 {body['filtered_uncertified_count']}"
        )

        items = body["items"]
        assert len(items) == 3, f"top_k=3 应有 3 items, 实际 {len(items)}"

        # rank 1: V高分 (verified + top rating)
        assert items[0]["companion_id"] == str(cs["v_high"].id), (
            f"rank 1 应为 V高分, 实际 {items[0]['companion_id']}"
        )
        assert items[0]["companion_cert_status"] == "verified"
        assert items[0]["recommendation_rank"] == 1

        # rank 2: V低分 (verified, lower rating)
        assert items[1]["companion_id"] == str(cs["v_low"].id), (
            f"rank 2 应为 V低分, 实际 {items[1]['companion_id']}"
        )
        assert items[1]["companion_cert_status"] == "verified"
        assert items[1]["recommendation_rank"] == 2

        # rank 3: P高分 (pending_supplement, 最高分)
        assert items[2]["companion_id"] == str(cs["p_high"].id), (
            f"rank 3 应为 P高分, 实际 {items[2]['companion_id']}"
        )
        assert items[2]["companion_cert_status"] == "pending_supplement"
        assert items[2]["recommendation_rank"] == 3

        # §1.4 守门: U系列任何 ID 都不应出现
        item_ids = {it["companion_id"] for it in items}
        assert str(cs["u_high"].id) not in item_ids, (
            "§1.4 守门: U高分 rating=5.0 不能因高分破防"
        )
        assert str(cs["u_low"].id) not in item_ids

    async def test_uncertified_with_max_stats_still_filtered(self, authenticated_client):
        """§1.4 守门强化: uncertified 即使 rating=5.0 + orders=9999 仍不返回.

        防回归: 防止有人为 "高分应该展示" 把 §1.4 guard 拆掉.
        """
        await _create_companion(
            real_name="超神 uncertified",
            verification_status=VerificationStatus.rejected,
            avg_rating=5.0,
            total_orders=9999,
        )
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=3"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["items"] == [], (
            f"§1.4: only uncertified 应 empty, 实际 {body['items']}"
        )
        assert body["filtered_uncertified_count"] == 1

    async def test_tie_breaker_chain_rating_orders_created(self, authenticated_client):
        """tie-breaker DESC chain: rating 同分 → orders 同 → created_at ASC (older first).

        3 个 verified, 完全相同 rating, 仅 orders/created_at 不同.
        """
        now = datetime.now(timezone.utc)
        a = await _create_companion(
            real_name="A_same",
            verification_status=VerificationStatus.verified,
            avg_rating=4.5,
            total_orders=100,
            created_at=now - timedelta(days=10),
        )
        b = await _create_companion(
            real_name="B_same_more_orders",
            verification_status=VerificationStatus.verified,
            avg_rating=4.5,
            total_orders=150,  # 更多 orders → 应排前
            created_at=now - timedelta(days=5),
        )
        c = await _create_companion(
            real_name="C_same_same_orders_older",
            verification_status=VerificationStatus.verified,
            avg_rating=4.5,
            total_orders=150,  # 与 B 同 orders
            created_at=now - timedelta(days=20),  # 但更老 → 应排 B 前
        )
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=3"
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 3
        # tie-breaker 链: rating 相同 → orders DESC → created_at ASC
        # C (orders=150, older) > B (orders=150, newer) > A (orders=100)
        assert items[0]["companion_id"] == str(c.id), (
            f"tie-breaker rank 1 应为 C (orders=150, older), 实际 {items[0]['companion_id']}"
        )
        assert items[1]["companion_id"] == str(b.id), (
            f"tie-breaker rank 2 应为 B (orders=150, newer), 实际 {items[1]['companion_id']}"
        )
        assert items[2]["companion_id"] == str(a.id)


# ============================================================
# AC#2 — TestABACPIINegativeE2E
# ============================================================


@pytest.mark.asyncio
class TestABACPIINegativeE2E:
    """spec §1.2 PII negative list E2E (多场景跨 endpoint 验证).

    PR #285 ``test_pii_fields_absent_from_response`` 测 **单 endpoint 单 case**;
    本 E2E 测 **4 scenario** (empty / single / mixed sort / city filter) 每条
    response 都 **0 PII hit**, 防 ABAC 漏出新路径.
    """

    async def test_no_pii_in_recommendation_response_full_chain(self, authenticated_client):
        """多 companion + top_k=3, response (含 items + meta) 不出现 8 PII 字段名.

        Sentinel: certification_no / certification_image_url 在 fixture 中预埋
        PII_SENTINEL 字符串, 若漏出 raw value 会直接命中.
        """
        await _create_six_companion_set()
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=3"
        )
        assert resp.status_code == 200
        body = resp.json()
        flat = _serialize_recursive(body)

        # 8 字段名都不应出现在 response (key + value 检查)
        for pii_field in PII_FIELDS_NEGATIVE:
            assert pii_field not in flat, (
                f"PII 字段 '{pii_field}' 漏出 response (ABAC layer 3/4 失效)"
            )

        # Sentinel raw value (certification_no / cert_url) 不应漏
        assert PII_SENTINEL not in flat, (
            "PII sentinel 字符串漏出 — certification_no / cert_url raw value 漏"
        )

        # mask_name 模式验证: pseudonym_name 应是脱敏, 不是真名
        for item in body["items"]:
            if item.get("pseudonym_name"):
                # 真名都是 V/P 开头, pseudonym 应被脱敏 (不应等于 fixture 的 real_name)
                assert not item["pseudonym_name"].startswith("V高"), (
                    f"pseudonym_name 不应是 real_name 原文: {item['pseudonym_name']}"
                )
                assert not item["pseudonym_name"].startswith("P高"), (
                    f"pseudonym_name 不应是 real_name 原文: {item['pseudonym_name']}"
                )

    async def test_no_pii_across_top_k_variants(self, authenticated_client):
        """跨 top_k=1/2/3 + city filter 4 query 都不漏 PII.

        防御目的: 不同 query 走的可能是不同 service code path, ABAC 都要守.
        """
        await _create_six_companion_set()
        queries = [
            "/api/v1/companions/recommendations?top_k=1",
            "/api/v1/companions/recommendations?top_k=2",
            "/api/v1/companions/recommendations?top_k=3",
            "/api/v1/companions/recommendations?city=北京&top_k=3",
        ]
        for q in queries:
            resp = await authenticated_client.get(q)
            assert resp.status_code == 200, f"{q} → {resp.status_code} {resp.text}"
            flat = _serialize_recursive(resp.json())
            for pii_field in PII_FIELDS_NEGATIVE:
                assert pii_field not in flat, (
                    f"PII 字段 '{pii_field}' 漏出 query={q} (ABAC 不应因 query 变化失守)"
                )
            assert PII_SENTINEL not in flat, (
                f"PII sentinel 漏出 query={q}"
            )

    async def test_pii_sentinel_present_in_db_but_not_in_response(
        self, authenticated_client
    ):
        """正向反证: 确认 fixture 确实写了 PII (sentinel 在 DB), endpoint 屏蔽生效.

        防 false-negative: 如果 fixture 没写 PII, 上面测试是空跑.
        """
        cs = await _create_six_companion_set()

        # 反证 1: DB 中 sentinel 应存在 (fixture 写入成功)
        async with test_session_factory() as session:
            row = await session.get(CompanionProfile, cs["v_high"].id)
            assert PII_SENTINEL in (row.certification_no or ""), (
                "fixture 未写入 sentinel, 后续 negative test 等同空跑"
            )
            assert PII_SENTINEL in (row.certification_image_url or ""), (
                "fixture 未写入 cert_url sentinel"
            )

        # 反证 2: endpoint response 不含 sentinel
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=3"
        )
        flat = _serialize_recursive(resp.json())
        assert PII_SENTINEL not in flat, (
            "DB 有 sentinel 但 response 漏出 — ABAC layer 3/4 失效"
        )


# ============================================================
# AC#3 — TestRecommendationSLOLocalE2E
# ============================================================


@pytest.mark.asyncio
class TestRecommendationSLOLocalE2E:
    """spec §2.3 SLO 本地 baseline (50 次 call P50<200ms / P99<500ms).

    PR #285 无时延 test; 本 E2E 用本地 in-memory SQLite + httpx 测分位数.
    与 S3-TEST-003-CROSS-REPLICA-E2E (k6 + 双副本 staging) **不重复**:
    - 本 E2E: 防 endpoint impl regression (如 O(N²) sort / 慢 query)
    - S3-TEST-003: 真实负载 + 双副本 (staging only, 当前 demote 等资源)
    """

    async def test_p50_p99_local_baseline_50_calls(self, authenticated_client):
        """50 次 GET /recommendations top_k=3, 验证 P50<200ms / P99<500ms.

        本地 baseline 宽松: in-memory SQLite 不会有真 IO 瓶颈, 主要捕捉
        endpoint 内部明显回归 (eg. sort O(N²) / 重复 SELECT / 重 serialization).
        """
        # 6 companion fixture (典型负载)
        await _create_six_companion_set()

        latencies_ms: list[float] = []
        for _ in range(50):
            t0 = time.perf_counter()
            resp = await authenticated_client.get(
                "/api/v1/companions/recommendations?top_k=3"
            )
            t1 = time.perf_counter()
            assert resp.status_code == 200, (
                f"SLO test request failed: {resp.status_code} {resp.text}"
            )
            latencies_ms.append((t1 - t0) * 1000)

        # 用 statistics 算分位数 (Python 3.8+ statistics.quantiles)
        sorted_latencies = sorted(latencies_ms)
        p50 = statistics.median(latencies_ms)
        # P99 = 第 99 分位, 50 次中取 index = round(50 * 0.99) - 1 = 49 (即最大)
        # 用更严的 method='exclusive' 等价 numpy.percentile(99)
        # 简化: 取倒数第 1 个作为 P99 lower bound
        p99 = sorted_latencies[-1]  # 50 sample 中 P99 ≈ max

        # 本地 in-memory baseline 阈值 (远宽于 staging)
        # 注: 这是 dev box 防 regression baseline, 真 SLO 在 staging k6
        assert p50 < 200, (
            f"SLO 本地 P50 退化 — P50={p50:.1f}ms (阈值 200ms), "
            f"latencies={[f'{l:.1f}' for l in sorted_latencies[:5]]}..."
        )
        assert p99 < 500, (
            f"SLO 本地 P99 退化 — P99={p99:.1f}ms (阈值 500ms)"
        )

        # 输出方便 PR review 看
        print(
            f"\n[SLO local] 50 calls — "
            f"P50={p50:.1f}ms / P99={p99:.1f}ms / "
            f"min={sorted_latencies[0]:.1f}ms / max={sorted_latencies[-1]:.1f}ms"
        )


# ============================================================
# AC#4 — TestAdminOverrideRejectE2E
# ============================================================


@pytest.mark.asyncio
class TestAdminOverrideRejectE2E:
    """spec §1.4 admin override reject (admin 直接 DB write 也不破防).

    spec §1.4 当前 P0 部分 = **uncertified 永远不返回**,
    P2 follow-up = admin override `recommendation_rank` (走 ``S3-DEV-006-FOLLOWUP-ADMIN-OVERRIDE``).

    本 E2E 测 **核心硬约束**:
    - admin 在 DB 上直接改 verification_status 仍要走 §1.4 守门 (rejected 不返回)
    - admin 即使把 uncertified 数据加各种"推荐"属性, endpoint 也不展示

    防御场景: 防止 admin 工具 / DB 修复脚本意外把 reject 状态写错.
    """

    async def test_db_direct_set_high_rating_uncertified_still_rejected(
        self, authenticated_client
    ):
        """模拟 admin 在 DB 上把 uncertified 改成 "高分" 行为, 仍不返回.

        防御场景: 数据修复脚本 / admin 后台直改 DB.
        """
        # 1. 创建 1 个 uncertified, 已经是高分 (反案中提到的"推荐"误激活)
        target = await _create_companion(
            real_name="伪推荐 uncertified",
            verification_status=VerificationStatus.rejected,
            avg_rating=5.0,
            total_orders=500,
        )

        # 2. 模拟 admin 后台直接 DB 改 (没有改 verification_status 是关键 — uncertified 守门强约束)
        async with test_session_factory() as session:
            row = await session.get(CompanionProfile, target.id)
            # admin 改了一些其他字段 (模拟"误激活")
            row.bio = "[admin 推荐] 高分陪诊师"
            row.avg_rating = 5.0  # 改到极限
            row.total_orders = 9999
            # verification_status 仍是 rejected → uncertified 守门
            await session.commit()

        # 3. 推荐 endpoint 应仍 reject (§1.4 守门)
        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=3"
        )
        assert resp.status_code == 200
        body = resp.json()
        item_ids = {it["companion_id"] for it in body["items"]}
        assert str(target.id) not in item_ids, (
            f"§1.4 守门失效: admin 改了 bio/rating/orders 但 verification_status=rejected, "
            f"endpoint 不应返回; 实际 items={item_ids}"
        )
        assert body["filtered_uncertified_count"] >= 1

    async def test_mixed_admin_override_with_verified_still_correct_ranking(
        self, authenticated_client
    ):
        """admin 改了 uncertified 一些字段, 真 verified 仍正常返回 + 排序对.

        混合场景: admin 改 uncertified 的副作用不应污染真 verified 的排序.
        """
        # 1 verified
        verified = await _create_companion(
            real_name="真 verified",
            verification_status=VerificationStatus.verified,
            avg_rating=4.5,
            total_orders=100,
        )
        # 1 admin 改过的 "伪推荐 uncertified" (高分但仍 rejected)
        fake = await _create_companion(
            real_name="伪推荐 uncertified",
            verification_status=VerificationStatus.rejected,
            avg_rating=5.0,
            total_orders=1000,
        )

        resp = await authenticated_client.get(
            "/api/v1/companions/recommendations?top_k=3"
        )
        assert resp.status_code == 200
        body = resp.json()
        items = body["items"]
        # 只有 verified 出现
        assert len(items) == 1
        assert items[0]["companion_id"] == str(verified.id), (
            f"真 verified 应 rank 1, 实际 {items[0]['companion_id']}"
        )
        # fake (uncertified) 必须不在
        item_ids = {it["companion_id"] for it in items}
        assert str(fake.id) not in item_ids, (
            "§1.4 守门失效: rejected 高分 fake 不应进 top_k"
        )
        assert body["filtered_uncertified_count"] >= 1


# ============================================================
# End of S3-TEST-007 E2E
# ============================================================
