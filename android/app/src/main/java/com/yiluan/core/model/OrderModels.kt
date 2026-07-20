package com.yiluan.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * 订单 / 支付 / 医院相关 DTO（对齐后端 orders/payments/hospitals + iOS Order Feature）。
 * ANDROID-DEV-B2-PATIENT — 患者核心闭环。
 *
 * 关键契约（见 design §3.4 §5 B2 + ADR-0041）：
 *  - 金额用 String（后端 Decimal(10,2) 序列化为字符串 "199.00"，不用 float/double）。
 *  - 订单状态机(status) 与支付副状态(payment_state) 解耦：created 单支付成功后
 *    status 仍 created，仅 payment_state=paid；陪诊师 accept 才 → accepted。
 *  - 全 snake_case 显式 @SerialName。
 */

// MARK: - 枚举

/** 订单业务状态（=DB OrderStatus=iOS，9 个真实值，勿用过时的 pending_payment/paid）。 */
enum class OrderStatus(val value: String) {
    CREATED("created"),
    ACCEPTED("accepted"),
    IN_PROGRESS("in_progress"),
    COMPLETED("completed"),
    REVIEWED("reviewed"),
    CANCELLED_BY_PATIENT("cancelled_by_patient"),
    CANCELLED_BY_COMPANION("cancelled_by_companion"),
    REJECTED_BY_COMPANION("rejected_by_companion"),
    EXPIRED("expired");

    companion object {
        fun fromValue(v: String?): OrderStatus? = entries.firstOrNull { it.value == v }
    }
}

/** 支付副状态（订单上的 payment_state，与 status 解耦）。 */
enum class PaymentState(val value: String) {
    NONE("none"),
    PAYING("paying"),
    PAID("paid"),
    FAILED("failed"),
    ABNORMAL("abnormal");

    companion object {
        fun fromValue(v: String?): PaymentState? = entries.firstOrNull { it.value == v }
    }
}

/** 服务类型。 */
enum class ServiceType(val value: String) {
    FULL_ACCOMPANY("full_accompany"),
    HALF_ACCOMPANY("half_accompany"),
    ERRAND("errand");

    companion object {
        fun fromValue(v: String?): ServiceType? = entries.firstOrNull { it.value == v }
    }
}

// MARK: - 订单

@Serializable
data class FamilyMember(
    @SerialName("id") val id: String,
    @SerialName("name") val name: String,
    @SerialName("relation") val relation: String? = null,
    @SerialName("phone") val phone: String? = null,
)

@Serializable
data class TimelineEntry(
    @SerialName("title") val title: String,
    @SerialName("time") val time: String? = null,
)

/**
 * 订单响应（对齐后端 OrderResponse）。金额字段用 String。
 */
@Serializable
data class Order(
    @SerialName("id") val id: String,
    @SerialName("order_number") val orderNumber: String,
    @SerialName("patient_id") val patientId: String,
    @SerialName("companion_id") val companionId: String? = null,
    @SerialName("hospital_id") val hospitalId: String,
    @SerialName("service_type") val serviceType: String,
    @SerialName("service_name_snapshot") val serviceNameSnapshot: String? = null,
    @SerialName("service_price_snapshot") val servicePriceSnapshot: String? = null,
    @SerialName("status") val status: String,
    @SerialName("appointment_date") val appointmentDate: String,
    @SerialName("appointment_time") val appointmentTime: String,
    @SerialName("description") val description: String? = null,
    @SerialName("price") val price: String,
    @SerialName("hospital_name") val hospitalName: String? = null,
    @SerialName("companion_name") val companionName: String? = null,
    @SerialName("patient_name") val patientName: String? = null,
    @SerialName("family_member") val familyMember: FamilyMember? = null,
    @SerialName("payment_status") val paymentStatus: String? = null,
    @SerialName("payment_state") val paymentState: String? = null,
    @SerialName("refund_state") val refundState: String? = null,
    @SerialName("expires_at") val expiresAt: String? = null,
    @SerialName("timeline") val timeline: List<TimelineEntry> = emptyList(),
    @SerialName("timeline_index") val timelineIndex: Int? = null,
    @SerialName("created_at") val createdAt: String? = null,
    @SerialName("updated_at") val updatedAt: String? = null,
)

// Order 计算属性抽为扩展（保持 @Serializable data class 纯数据，规避 KSP/serialization 插件
// 对 data class body 内计算属性 + 同文件 enum 引用的解析问题）。

val Order.orderStatus: OrderStatus? get() = OrderStatus.fromValue(status)
val Order.paymentStateEnum: PaymentState? get() = PaymentState.fromValue(paymentState)
val Order.serviceTypeEnum: ServiceType? get() = ServiceType.fromValue(serviceType)

/** 患者是否可发起支付：created 态且未支付。 */
val Order.canPay: Boolean
    get() = orderStatus == OrderStatus.CREATED && paymentStateEnum != PaymentState.PAID

/** 患者是否可取消：created/accepted/in_progress。 */
val Order.canCancel: Boolean
    get() = orderStatus in setOf(
        OrderStatus.CREATED, OrderStatus.ACCEPTED, OrderStatus.IN_PROGRESS,
    )

@Serializable
data class OrderListResponse(
    @SerialName("items") val items: List<Order> = emptyList(),
    @SerialName("total") val total: Int = 0,
)

@Serializable
data class CreateOrderRequest(
    @SerialName("service_type") val serviceType: String,
    @SerialName("hospital_id") val hospitalId: String,
    @SerialName("appointment_date") val appointmentDate: String,
    @SerialName("appointment_time") val appointmentTime: String,
    @SerialName("description") val description: String? = null,
    @SerialName("companion_id") val companionId: String? = null,
    @SerialName("family_member_id") val familyMemberId: String? = null,
)

// MARK: - 支付

/**
 * 发起支付响应（后端 /orders/{id}/pay 真实返回体，非 Payment 模型）。
 * mock provider 下 mockSuccess=true 即支付成功，随后 loadOrder 复查 payment_state。
 */
@Serializable
data class PrepayResponse(
    @SerialName("payment_id") val paymentId: String,
    @SerialName("provider") val provider: String,
    @SerialName("prepay_id") val prepayId: String? = null,
    @SerialName("mock_success") val mockSuccess: Boolean = false,
)

// MARK: - 医院

@Serializable
data class Hospital(
    @SerialName("id") val id: String,
    @SerialName("name") val name: String,
    @SerialName("address") val address: String? = null,
    @SerialName("level") val level: String? = null,
    @SerialName("province") val province: String? = null,
    @SerialName("city") val city: String? = null,
    @SerialName("district") val district: String? = null,
    @SerialName("tags") val tags: String? = null,
    @SerialName("latitude") val latitude: Double? = null,
    @SerialName("longitude") val longitude: Double? = null,
) {
    /** 逗号分隔 tags 拆成 list（对齐 iOS tagList）。 */
    val tagList: List<String>
        get() = tags?.split(",")?.map(String::trim)?.filter(String::isNotEmpty) ?: emptyList()
}

@Serializable
data class HospitalListResponse(
    @SerialName("items") val items: List<Hospital> = emptyList(),
    @SerialName("total") val total: Int = 0,
)
