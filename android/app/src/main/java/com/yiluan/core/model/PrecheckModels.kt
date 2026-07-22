package com.yiluan.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Precheck 信任卡 DTO（对齐后端 OrderPrecheckSummaryView + iOS Precheck）。
 * ANDROID-DEV-B5-PRECHECK-SHARE — 4 信任卡 + WS 推送刷新。
 *
 * ⚠️ ABAC positive-list：只声明后端会返回的字段。negative-list 17 字段（真名/身份证/
 *    手机/raw_llm_output/cost 等）后端永不返回，Android DTO 也不声明。
 *    signed URL TTL ≤15min，用时即取不缓存。
 */

// MARK: - 4 信任卡

@Serializable
data class ContractStatusCard(
    @SerialName("ready") val ready: Boolean = false,
    @SerialName("contract_id") val contractId: String? = null,
    @SerialName("contract_template_version") val contractTemplateVersion: String? = null,
    @SerialName("contract_pdf_url") val contractPdfUrl: String? = null,
    @SerialName("generated_at") val generatedAt: String? = null,
)

@Serializable
data class InsuranceStatusCard(
    @SerialName("ready") val ready: Boolean = false,
    @SerialName("insurance_order_id") val insuranceOrderId: String? = null,
    @SerialName("insurance_policy_no_masked") val insurancePolicyNoMasked: String? = null,
    @SerialName("insurance_policy_pdf_url") val insurancePolicyPdfUrl: String? = null,
    @SerialName("insurance_effective_from") val insuranceEffectiveFrom: String? = null,
)

@Serializable
data class PreparationStatusCard(
    @SerialName("ready") val ready: Boolean = false,
    @SerialName("preparation_id") val preparationId: String? = null,
    @SerialName("prep_summary") val prepSummary: String? = null,
    @SerialName("sections_count") val sectionsCount: Int? = null,
    @SerialName("generated_at") val generatedAt: String? = null,
)

@Serializable
data class CompanionCertStatusCard(
    @SerialName("ready") val ready: Boolean = false,
    @SerialName("companion_cert_pseudonym_name") val pseudonymName: String? = null,
    @SerialName("companion_cert_work_id") val workId: String? = null,
    @SerialName("companion_cert_qualifications") val qualifications: List<String> = emptyList(),
    @SerialName("companion_cert_proof_image_urls") val proofImageUrls: List<String> = emptyList(),
    @SerialName("companion_cert_verified_at") val verifiedAt: String? = null,
)

// MARK: - Summary

@Serializable
data class OrderPrecheckSummary(
    @SerialName("order_id") val orderId: String,
    @SerialName("contract_status") val contractStatus: ContractStatusCard? = null,
    @SerialName("insurance_status") val insuranceStatus: InsuranceStatusCard? = null,
    @SerialName("preparation_status") val preparationStatus: PreparationStatusCard? = null,
    @SerialName("companion_cert_status") val companionCertStatus: CompanionCertStatusCard? = null,
    @SerialName("all_ready") val allReady: Boolean = false,
    /** 与 all_ready 解耦：付款是否放行。 */
    @SerialName("payment_enabled") val paymentEnabled: Boolean = false,
    @SerialName("blocked_reason") val blockedReason: String? = null,
    @SerialName("signed_url_expires_at") val signedUrlExpiresAt: String? = null,
)

// MARK: - Precheck WS 事件（用 event 字段，payload 仅 invalidate 信号 → 重拉 HTTP）

@Serializable
data class PrecheckWsFrame(
    /** 控制帧 type: auth/auth_ok/ping/pong。 */
    @SerialName("type") val type: String? = null,
    /** 业务事件 event: precheck.status.updated/all_ready/blocked。 */
    @SerialName("event") val event: String? = null,
)
