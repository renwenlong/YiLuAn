package com.yiluan.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * 实时（chat + notification）DTO + WS 帧封装。
 * ANDROID-DEV-B4-REALTIME — 对齐后端 WS/REST 契约 + iOS Chat/Notifications。
 *
 * WS 帧协议（subagent 调研核实）：
 *  - 上行: {type:"auth"|"ping"|"text"|"image"|"system", ...}
 *  - 下行控制帧: {type:"auth_ok"|"pong"|"unread_count_changed", count?}
 *  - 下行消息/通知帧: DTO 本体(snake_case)，其 type 字段是消息/通知类型枚举(非控制字)
 *  → 按 type 分派：控制帧忽略/更新角标，其余按 DTO 解析。
 */

// MARK: - Chat 消息

/** 消息类型：text/image(content=url)/system。 */
enum class ChatMessageType(val value: String) {
    TEXT("text"), IMAGE("image"), SYSTEM("system");
    companion object {
        fun fromValue(v: String?): ChatMessageType = entries.firstOrNull { it.value == v } ?: TEXT
    }
}

@Serializable
data class ChatMessage(
    @SerialName("id") val id: String,
    @SerialName("order_id") val orderId: String,
    @SerialName("sender_id") val senderId: String,
    @SerialName("type") val type: String = "text",
    @SerialName("content") val content: String,
    @SerialName("is_read") val isRead: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("nonce") val nonce: String? = null,
) {
    val messageType: ChatMessageType get() = ChatMessageType.fromValue(type)
}

@Serializable
data class ChatMessageListResponse(
    @SerialName("items") val items: List<ChatMessage> = emptyList(),
    @SerialName("total") val total: Int = 0,
    @SerialName("has_more") val hasMore: Boolean = false,
    @SerialName("next_before_id") val nextBeforeId: String? = null,
)

@Serializable
data class ChatBackfillResponse(
    @SerialName("items") val items: List<ChatMessage> = emptyList(),
    @SerialName("next_after_id") val nextAfterId: String? = null,
    @SerialName("has_more") val hasMore: Boolean = false,
)

@Serializable
data class SendChatMessageRequest(
    @SerialName("content") val content: String,
    @SerialName("type") val type: String = "text",
)

@Serializable
data class MarkReadResponse(
    @SerialName("marked_read") val markedRead: Int = 0,
)

// MARK: - Notification

enum class NotificationType(val value: String) {
    ORDER_STATUS_CHANGED("order_status_changed"),
    NEW_MESSAGE("new_message"),
    NEW_ORDER("new_order"),
    REVIEW_RECEIVED("review_received"),
    SYSTEM("system");
    companion object {
        fun fromValue(v: String?): NotificationType = entries.firstOrNull { it.value == v } ?: SYSTEM
    }
}

@Serializable
data class Notification(
    @SerialName("id") val id: String,
    @SerialName("user_id") val userId: String? = null,
    @SerialName("type") val type: String = "system",
    @SerialName("title") val title: String? = null,
    @SerialName("body") val body: String? = null,
    @SerialName("reference_id") val referenceId: String? = null,
    @SerialName("target_type") val targetType: String? = null,
    @SerialName("target_id") val targetId: String? = null,
    @SerialName("is_read") val isRead: Boolean = false,
    @SerialName("created_at") val createdAt: String? = null,
) {
    val notificationType: NotificationType get() = NotificationType.fromValue(type)
}

@Serializable
data class NotificationListResponse(
    @SerialName("items") val items: List<Notification> = emptyList(),
    @SerialName("total") val total: Int = 0,
)

@Serializable
data class UnreadCountResponse(
    @SerialName("count") val count: Int = 0,
)

// MARK: - WS 帧封装

/**
 * WS 帧 type 判别（只解析 type 字段，用于分派）。
 * 消息/通知帧的 type 是业务枚举(text/order_status_changed 等)，控制帧是 auth_ok/pong/unread_count_changed。
 */
@Serializable
data class WsFrameEnvelope(
    @SerialName("type") val type: String? = null,
    @SerialName("count") val count: Int? = null,
)

/** 上行 auth 首帧。 */
@Serializable
data class WsAuthFrame(
    @SerialName("type") val type: String = "auth",
    @SerialName("token") val token: String,
)

/** 上行 ping 帧。 */
@Serializable
data class WsPingFrame(
    @SerialName("type") val type: String = "ping",
)

/** 上行发消息帧（chat）。 */
@Serializable
data class WsSendMessageFrame(
    @SerialName("type") val type: String,
    @SerialName("content") val content: String,
    @SerialName("nonce") val nonce: String,
)
