package com.yiluan.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * 陪诊员相关 DTO（对齐后端 companions + iOS Companion Feature）。
 * ANDROID-DEV-B3-COMPANION — 陪诊员闭环: 入驻/档案/统计/公开详情。
 *
 * 关键契约（subagent 调研核实）：
 *  - 公开详情 companions/{id} ABAC 脱敏（pseudonym_name 化名，无 real_name/id_number）。
 *  - 本人 companions/me 含 real_name + 全认证字段。
 *  - 金额/评分: total_earnings 用 String(Decimal), avg_rating 0-5 Double。
 *  - 全 snake_case 显式 @SerialName。
 */

// MARK: - 维度评分

@Serializable
data class DimensionScores(
    @SerialName("punctuality") val punctuality: Double? = null,
    @SerialName("professionalism") val professionalism: Double? = null,
    @SerialName("communication") val communication: Double? = null,
    @SerialName("attitude") val attitude: Double? = null,
)

// MARK: - 陪诊员详情（本人 me / 公开 {id} 复用；脱敏字段本人非空、公开为 null）

@Serializable
data class CompanionProfile(
    @SerialName("id") val id: String,
    @SerialName("user_id") val userId: String? = null,
    /** 本人可见真名；公开视角为 null。 */
    @SerialName("real_name") val realName: String? = null,
    /** 公开视角化名（张**）；本人视角可能为 null。 */
    @SerialName("pseudonym_name") val pseudonymName: String? = null,
    @SerialName("id_number") val idNumber: String? = null,
    @SerialName("service_area") val serviceArea: String? = null,
    @SerialName("service_types") val serviceTypes: String? = null,
    @SerialName("service_hospitals") val serviceHospitals: String? = null,
    @SerialName("service_city") val serviceCity: String? = null,
    @SerialName("bio") val bio: String? = null,
    @SerialName("avg_rating") val avgRating: Double = 0.0,
    @SerialName("total_orders") val totalOrders: Int = 0,
    @SerialName("verification_status") val verificationStatus: String? = null,
    @SerialName("certifications") val certifications: String? = null,
    @SerialName("certification_type") val certificationType: String? = null,
    @SerialName("certified_at") val certifiedAt: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("dimension_scores") val dimensionScores: DimensionScores? = null,
    @SerialName("created_at") val createdAt: String? = null,
) {
    /** 服务类型逗号拆 list。 */
    val serviceTypeList: List<String>
        get() = serviceTypes?.split(",")?.map(String::trim)?.filter(String::isNotEmpty) ?: emptyList()

    /** 是否已认证通过。 */
    val isVerified: Boolean get() = verificationStatus == "verified"

    /** 展示名：优先化名（公开），否则真名。 */
    val displayName: String get() = pseudonymName ?: realName ?: ""
}

// MARK: - 脱敏列表项（目录）

@Serializable
data class CompanionDirectoryItem(
    @SerialName("id") val id: String,
    @SerialName("pseudonym_name") val pseudonymName: String? = null,
    @SerialName("service_area") val serviceArea: String? = null,
    @SerialName("service_types") val serviceTypes: String? = null,
    @SerialName("service_city") val serviceCity: String? = null,
    @SerialName("avg_rating") val avgRating: Double = 0.0,
    @SerialName("total_orders") val totalOrders: Int = 0,
    @SerialName("verification_status") val verificationStatus: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
)

@Serializable
data class CompanionListResponse(
    @SerialName("items") val items: List<CompanionDirectoryItem> = emptyList(),
    @SerialName("total") val total: Int = 0,
)

// MARK: - 统计

@Serializable
data class CompanionStats(
    @SerialName("open_orders") val openOrders: Int = 0,
    @SerialName("total_orders") val totalOrders: Int = 0,
    @SerialName("avg_rating") val avgRating: Double = 0.0,
    @SerialName("total_earnings") val totalEarnings: String = "0.00",
)

// MARK: - 入驻 / 更新档案请求

@Serializable
data class ApplyCompanionRequest(
    @SerialName("real_name") val realName: String,
    @SerialName("service_types") val serviceTypes: String,
    @SerialName("id_number") val idNumber: String? = null,
    @SerialName("certifications") val certifications: String? = null,
    @SerialName("service_area") val serviceArea: String? = null,
    @SerialName("service_hospitals") val serviceHospitals: String? = null,
    @SerialName("service_city") val serviceCity: String? = null,
    @SerialName("bio") val bio: String? = null,
)

@Serializable
data class UpdateCompanionProfileRequest(
    @SerialName("service_area") val serviceArea: String? = null,
    @SerialName("service_types") val serviceTypes: String? = null,
    @SerialName("bio") val bio: String? = null,
    @SerialName("certifications") val certifications: String? = null,
    @SerialName("service_hospitals") val serviceHospitals: String? = null,
    @SerialName("service_city") val serviceCity: String? = null,
)
