package com.yiluan.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * Share DTO（发起端 owner + 接收端访客脱敏视图）。
 * ANDROID-DEV-B5-PRECHECK-SHARE — 对齐后端 share.py + iOS Share Feature。
 *
 * 发起端需 access_token；接收端 OTP/exchange requiresAuth=false，脱敏订单用 share_session header。
 * 全 snake_case。ABAC 脱敏：接收端视图无患者电话/身份证/病情。
 */

// MARK: - ShareScope

enum class ShareScope(val value: String) {
    FULL("full"), PROGRESS_ONLY("progress_only");
    companion object {
        fun fromValue(v: String?): ShareScope = entries.firstOrNull { it.value == v } ?: PROGRESS_ONLY
    }
}

// MARK: - 发起端 token（7 字段必测）

@Serializable
data class OrderShareToken(
    @SerialName("id") val id: String,
    @SerialName("share_token") val shareToken: String,
    @SerialName("share_url") val shareUrl: String,
    @SerialName("share_scope") val shareScope: String,
    @SerialName("share_expires_at") val shareExpiresAt: String? = null,
    @SerialName("share_revoked_at") val shareRevokedAt: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("first_accessed_at") val firstAccessedAt: String? = null,
    @SerialName("distinct_accessor_count") val distinctAccessorCount: Int = 0,
) {
    val scope: ShareScope get() = ShareScope.fromValue(shareScope)
    val isRevoked: Boolean get() = shareRevokedAt != null
}

@Serializable
data class CreateShareRequest(
    @SerialName("share_scope") val shareScope: String,
)

@Serializable
data class CreateShareResponse(
    @SerialName("id") val id: String,
    @SerialName("share_token") val shareToken: String,
    @SerialName("share_url") val shareUrl: String,
    @SerialName("share_scope") val shareScope: String,
    @SerialName("share_expires_at") val shareExpiresAt: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("share_active_count") val shareActiveCount: Int = 0,
)

@Serializable
data class ListSharesResponse(
    @SerialName("items") val items: List<OrderShareToken> = emptyList(),
    @SerialName("share_active_count") val shareActiveCount: Int = 0,
)

// MARK: - 接收端 OTP + exchange

@Serializable
data class ShareSendOtpRequest(
    @SerialName("phone") val phone: String,
)

@Serializable
data class ShareSendOtpResponse(
    @SerialName("sent") val sent: Boolean = false,
    @SerialName("masked_phone") val maskedPhone: String? = null,
    @SerialName("expires_in") val expiresIn: Int = 0,
)

@Serializable
data class ExchangeSessionRequest(
    @SerialName("phone") val phone: String,
    @SerialName("otp") val otp: String,
)

@Serializable
data class ExchangeSessionResponse(
    @SerialName("share_session") val shareSession: String,
    @SerialName("share_session_expires_at") val shareSessionExpiresAt: String? = null,
    @SerialName("share_scope") val shareScope: String,
    @SerialName("order_id") val orderId: String,
)

// MARK: - 接收端脱敏订单视图

@Serializable
data class ShareCompanionView(
    @SerialName("name") val name: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
)

@Serializable
data class ShareTimelineItem(
    @SerialName("at") val at: String? = null,
    @SerialName("event") val event: String? = null,
    @SerialName("detail") val detail: String? = null,
)

@Serializable
data class ShareOrderResponse(
    @SerialName("order_id") val orderId: String,
    @SerialName("order_number") val orderNumber: String? = null,
    @SerialName("status") val status: String? = null,
    @SerialName("service_type") val serviceType: String? = null,
    @SerialName("appointment_date") val appointmentDate: String? = null,
    @SerialName("appointment_time") val appointmentTime: String? = null,
    @SerialName("hospital_name") val hospitalName: String? = null,
    @SerialName("patient_name_masked") val patientNameMasked: String? = null,
    @SerialName("companion") val companion: ShareCompanionView? = null,
    @SerialName("share_scope") val shareScope: String? = null,
    @SerialName("can_view_images") val canViewImages: Boolean = false,
    @SerialName("can_view_ai_summary") val canViewAiSummary: Boolean = false,
    @SerialName("timeline") val timeline: List<ShareTimelineItem> = emptyList(),
)

// MARK: - Share WS 帧（first-frame share_auth，protocol ping）

/** 上行 share_auth 首帧。 */
@Serializable
data class ShareAuthFrame(
    @SerialName("type") val type: String = "share_auth",
    @SerialName("session") val session: String,
)

/** 下行帧判别（share_auth_ok/share_auth_err/业务事件）。 */
@Serializable
data class ShareWsFrame(
    @SerialName("type") val type: String? = null,
    @SerialName("reason") val reason: String? = null,
    @SerialName("event") val event: String? = null,
)
