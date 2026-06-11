import Foundation

/// 4 信任卡 precheck summary model — iOS 端契约
///
/// **S3-DEV-003-TRUST-UI-IOS (方案 B canonical — 纯 Swift Native)**
///
/// 跨端字段契约: 字段名 + 类型 + 可选性 与
/// `backend/app/schemas/order_precheck.py::OrderPrecheckSummaryView` 一致
/// (后端 ADR-0046 §3.5 positive-list + ABAC Layer 1 物理 schema 排除).
///
/// **ABAC negative-list 17 字段** (后端永不返回, iOS 端也永不解码):
/// - Contract: `contract_hash` / `hash_inputs` / `storage_blob_path` / `template_key`
/// - Insurance: `carrier_internal_id` / `actual_premium` / `underwriter_meta`
/// - Preparation: `prompt_version` / `model_used` / `raw_llm_output` / `cost_yuan`
/// - Companion: `companion_real_name` / `companion_id_card_hash` / `companion_phone` /
///   `companion_user_id` (+ pattern `companion_real_*` / `*_id_card_*`)
///
/// **Signed URL TTL ≤15min** (`signed_url_expires_at` 字段标识全部 URL 中最早过期时间).
///
/// APIClient 配置 `keyDecodingStrategy = .convertFromSnakeCase`, 故 Swift
/// 字段用 camelCase, 后端 snake_case 自动映射.

// MARK: - Contract Card

/// 合同卡 — 仅 positive-list 字段
///
/// 后端 `ContractStatusView` (`backend/app/schemas/order_precheck.py:51`).
/// `ready=true` ⟺ ContractStatus == active (WORM 已存, signed URL 可用).
struct ContractStatusCard: Codable, Equatable {
    let ready: Bool
    let contractId: String?
    let contractTemplateVersion: String?

    /// Signed URL, TTL ≤15min. 用户点 "查看合同 PDF" 时打开.
    /// **不暴露原图 URL** — 这是 signed URL, 过期后失效, 后端 ABAC Layer 1.
    let contractPdfUrl: String?
    let generatedAt: Date?
}

// MARK: - Insurance Card

/// 保险卡 — 仅 positive-list 字段
///
/// 后端 `InsuranceStatusView` (`backend/app/schemas/order_precheck.py:77`).
/// `ready=true` ⟺ ServiceInsuranceRecord.status == active.
///
/// 字段名用 `insurance_*` prefix (ADR-0046 §3.5 + 胡桃 r2 amend,
/// 避免与 admin-side `policy_*` 字段 collide).
struct InsuranceStatusCard: Codable, Equatable {
    let ready: Bool
    let insuranceOrderId: String?

    /// 保单号脱敏: 头 4 + **** + 尾 4 (例 BX2026****1234).
    /// 后端已脱敏返回, iOS 不二次处理.
    let insurancePolicyNoMasked: String?

    /// Signed URL, TTL ≤15min.
    let insurancePolicyPdfUrl: String?
    let insuranceEffectiveFrom: String?  // backend 返回 date (YYYY-MM-DD), 不用 Date 避免 TZ 漂移
}

// MARK: - Preparation Card

/// AI 准备包卡 — 仅 positive-list 字段
///
/// 后端 `PreparationStatusView` (`backend/app/schemas/order_precheck.py:108`).
/// `ready=true` ⟺ PreparationPackage.status 是 active 或 active_fallback_template.
struct PreparationStatusCard: Codable, Equatable {
    let ready: Bool
    let preparationId: String?

    /// 已过 ABAC + 关键词过滤的摘要文本.
    let prepSummary: String?
    let sectionsCount: Int?
    let generatedAt: Date?
}

// MARK: - Companion Cert Card

/// 陪诊师资质卡 — 仅 positive-list 字段
///
/// 后端 `CompanionCertStatusView` (`backend/app/schemas/order_precheck.py:131`).
/// `ready=true` ⟺ CompanionProfile.verification_status == verified.
///
/// 字段名用 `companion_cert_*` prefix (ADR-0046 §3.5 positive-list lint).
struct CompanionCertStatusCard: Codable, Equatable {
    let ready: Bool

    /// 化名: e.g. "陈师傅", **不出真名** (ABAC defense).
    /// 后端 ABAC Layer 1 物理排除 `companion_real_name`, iOS 也不解码.
    let companionCertPseudonymName: String?

    /// 工号: e.g. "PC0042".
    let companionCertWorkId: String?

    /// 资质列表: ["康复治疗师", "健康管理师"].
    let companionCertQualifications: [String]?

    /// 资质证明图 signed URL, TTL ≤15min.
    let companionCertProofImageUrls: [String]?

    /// admin verify 通过那一刻的 timestamp.
    let companionCertVerifiedAt: Date?
}

// MARK: - Summary

/// 订单 4 信任卡聚合视图 — 用户付款前看
///
/// 后端 `OrderPrecheckSummaryView` (`backend/app/schemas/order_precheck.py:174`).
/// 由 `GET /api/v1/users/orders/{order_id}/precheck-status` 返回 +
/// `/ws/v1/orders/{order_id}/precheck` 推送 (3 event 类型).
///
/// `paymentEnabled` 跟 `allReady` 解耦, 允许 PM 侧 payment-pause overrides.
/// `blockedReason` 在任一 card `ready=false` 时填, 短文案 (design §3.3 文案 lint).
struct OrderPrecheckSummary: Codable, Equatable {
    let orderId: String

    let contractStatus: ContractStatusCard
    let insuranceStatus: InsuranceStatusCard
    let preparationStatus: PreparationStatusCard
    let companionCertStatus: CompanionCertStatusCard

    let allReady: Bool
    let paymentEnabled: Bool
    let blockedReason: String?

    /// 所有 signed URL 中最早过期时间 (max-min).
    /// 前端用来判 polling 时是否需要 refresh URL. TTL >15min 的 URL 后端 CI fail.
    let signedUrlExpiresAt: Date?
}

// MARK: - WS Event (3 types)

/// WS 推送 event 类型 (后端 `precheck_broadcast.py` 定义).
enum PrecheckEventType: String, Codable {
    case statusUpdated = "precheck.status.updated"
    case allReady = "precheck.all_ready"
    case blocked = "precheck.blocked"
}

/// WS 推送 envelope (后端 `_publish` 函数返回 schema).
///
/// payload 结构在 3 个 event 类型间不一致, 用 raw `[String: Any]` (via JSONSerialization)
/// 在 ViewModel 层 hand-roll dispatch:
/// - `status.updated`: 单 card 状态更新, 携带 card 名 + ready/blocked_reason
/// - `all_ready`: 4 card 全 ready, payment_enabled=true 信号
/// - `blocked`: 至少 1 card ready=false, 携带 blocked_reason
///
/// 收到任一 event 后 ViewModel 应当**重新 GET HTTP** 拿最新 summary
/// (WS 仅是 invalidate 信号, 不是完整 payload).
struct PrecheckWSEvent {
    let event: PrecheckEventType
    let rawPayload: [String: Any]
}
