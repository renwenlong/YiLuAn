package com.yiluan.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * 长尾功能 DTO（family-members / emergency-contacts / wallet / review / followup）。
 * ANDROID-DEV-B6-LONGTAIL — 对齐后端 + iOS Profile/Review Feature。
 * 金额用 String(Decimal 元), 全 snake_case 显式 @SerialName。
 */

// MARK: - 家庭成员（B6 管理用完整版；OrderModels.FamilyMember 是订单嵌套快照，勿混）

@Serializable
data class FamilyMemberProfile(
    @SerialName("id") val id: String,
    @SerialName("user_id") val userId: String? = null,
    @SerialName("name") val name: String,
    @SerialName("relation") val relation: String = "other",
    @SerialName("phone") val phone: String? = null,
    @SerialName("gender") val gender: String = "unknown",
    @SerialName("age") val age: Int? = null,
    @SerialName("medical_notes") val medicalNotes: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class FamilyMemberListResponse(
    @SerialName("items") val items: List<FamilyMemberProfile> = emptyList(),
    @SerialName("total") val total: Int = 0,
)

@Serializable
data class FamilyMemberRequest(
    @SerialName("name") val name: String,
    @SerialName("relation") val relation: String = "other",
    @SerialName("phone") val phone: String? = null,
    @SerialName("gender") val gender: String = "unknown",
    @SerialName("age") val age: Int? = null,
    @SerialName("medical_notes") val medicalNotes: String? = null,
)

// MARK: - 紧急联系人（GET 返回裸 list，无分页 wrapper）

@Serializable
data class EmergencyContact(
    @SerialName("id") val id: String,
    @SerialName("user_id") val userId: String? = null,
    @SerialName("name") val name: String,
    @SerialName("phone") val phone: String,
    @SerialName("relationship") val relationship: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class EmergencyContactRequest(
    @SerialName("name") val name: String,
    @SerialName("phone") val phone: String,
    @SerialName("relationship") val relationship: String? = null,
)

// MARK: - 钱包

@Serializable
data class WalletSummary(
    @SerialName("balance") val balance: String = "0.00",
    @SerialName("total_income") val totalIncome: String = "0.00",
    @SerialName("total_expense") val totalExpense: String = "0.00",
    @SerialName("withdrawable") val withdrawable: String = "0.00",
)

@Serializable
data class PaymentTransaction(
    @SerialName("id") val id: String,
    @SerialName("order_id") val orderId: String? = null,
    @SerialName("amount") val amount: String = "0.00",
    @SerialName("payment_type") val paymentType: String? = null,
    @SerialName("status") val status: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class TransactionListResponse(
    @SerialName("items") val items: List<PaymentTransaction> = emptyList(),
    @SerialName("total") val total: Int = 0,
)

// MARK: - 评价（review 提交驱动订单 completed→reviewed，业务功能）

/**
 * 创建评价请求（多维度模式：4 维度同时提供，后端加权平均出 rating）。
 * content 必填 5~500 字。
 */
@Serializable
data class CreateReviewRequest(
    @SerialName("punctuality_rating") val punctualityRating: Int,
    @SerialName("professionalism_rating") val professionalismRating: Int,
    @SerialName("communication_rating") val communicationRating: Int,
    @SerialName("attitude_rating") val attitudeRating: Int,
    @SerialName("content") val content: String,
)

@Serializable
data class ReviewResponse(
    @SerialName("id") val id: String,
    @SerialName("order_id") val orderId: String,
    @SerialName("companion_id") val companionId: String? = null,
    @SerialName("rating") val rating: Double = 0.0,
    @SerialName("content") val content: String? = null,
    @SerialName("patient_name") val patientName: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
)

// MARK: - 复诊提醒

@Serializable
data class FollowupReminder(
    @SerialName("id") val id: String,
    @SerialName("order_id") val orderId: String,
    @SerialName("remind_at") val remindAt: String,
    @SerialName("note") val note: String? = null,
    @SerialName("status") val status: String? = null,
    @SerialName("attempts") val attempts: Int? = null,
    @SerialName("sent_at") val sentAt: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
)

@Serializable
data class FollowupReminderListResponse(
    @SerialName("items") val items: List<FollowupReminder> = emptyList(),
    @SerialName("total") val total: Int = 0,
)

@Serializable
data class CreateFollowupReminderRequest(
    @SerialName("order_id") val orderId: String,
    @SerialName("remind_at") val remindAt: String,
    @SerialName("note") val note: String? = null,
)

// MARK: - 绑手机

@Serializable
data class BindPhoneRequest(
    @SerialName("phone") val phone: String,
    @SerialName("code") val code: String,
)
