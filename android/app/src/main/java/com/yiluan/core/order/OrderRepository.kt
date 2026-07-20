package com.yiluan.core.order

import com.yiluan.core.model.CreateOrderRequest
import com.yiluan.core.model.Order
import com.yiluan.core.model.PaymentState
import com.yiluan.core.model.PrepayResponse
import com.yiluan.core.model.paymentStateEnum
import com.yiluan.core.network.OrderApi
import javax.inject.Inject
import javax.inject.Singleton

/** 支付结果（对齐后端支付/业务状态解耦：mock 成功后 status 仍 created，payment_state=paid）。 */
data class PayResult(
    val success: Boolean,
    /** 支付后复查的最新订单（成功时非空）。 */
    val order: Order? = null,
)

/**
 * 订单仓库：封装下单 / 列表 / 详情 / 支付 / 取消。
 * ANDROID-DEV-B2-PATIENT — 对齐 iOS OrderViewModel 后端交互序列。
 *
 * 支付关键（ADR-0041 支付/业务状态解耦）：
 *  pay 返回 prepay 体，mock provider 下 mockSuccess=true 即支付成功；
 *  随后复查 GET /orders/{id} 确认 payment_state=paid（业务 status 仍 created，待接单）。
 */
@Singleton
class OrderRepository @Inject constructor(
    private val orderApi: OrderApi,
) {
    suspend fun createOrder(request: CreateOrderRequest): Order =
        orderApi.createOrder(request)

    suspend fun listOrders(status: String? = null, page: Int = 1): List<Order> =
        orderApi.listOrders(status = status, page = page, pageSize = 20).items

    suspend fun getOrder(orderId: String): Order =
        orderApi.getOrder(orderId)

    /**
     * 发起支付并确认结果。
     * mock provider: prepay.mockSuccess=true → 复查订单确认 payment_state=paid。
     * 返回 PayResult(success, 最新订单)。
     */
    suspend fun payOrder(orderId: String): PayResult {
        val prepay: PrepayResponse = orderApi.pay(orderId)
        if (!prepay.mockSuccess) {
            return PayResult(success = false)
        }
        // 复查订单确认支付副状态（对齐"无独立查支付端点，靠 GET /orders 复查 payment_state"）。
        val refreshed = orderApi.getOrder(orderId)
        val paid = refreshed.paymentStateEnum == PaymentState.PAID
        return PayResult(success = paid, order = refreshed)
    }

    suspend fun cancelOrder(orderId: String): Order =
        orderApi.cancel(orderId)
}
