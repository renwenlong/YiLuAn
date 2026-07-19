package com.yiluan.core.network

import com.yiluan.core.model.CreateOrderRequest
import com.yiluan.core.model.Order
import com.yiluan.core.model.OrderListResponse
import com.yiluan.core.model.PrepayResponse
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * 订单 API（需登录，走挂 AuthInterceptor 的业务 Retrofit）。
 * ANDROID-DEV-B2-PATIENT — 患者核心闭环: 创建/列表/详情/支付/取消。
 *
 * 对齐后端 orders.py + iOS OrderViewModel。列表 GET /orders 按 token 身份
 * 自动区分患者/陪诊师视角（无需传角色）。支付 /pay 返回 prepay 体（非 Payment 模型）。
 */
interface OrderApi {
    /** 创建订单，返回 status=created 的订单。 */
    @POST("orders")
    suspend fun createOrder(@Body body: CreateOrderRequest): Order

    /**
     * 订单列表（按 token 身份区分视角）。
     * @param status 可选状态过滤（created/in_progress/completed 等真实枚举值）。
     */
    @GET("orders")
    suspend fun listOrders(
        @Query("status") status: String? = null,
        @Query("page") page: Int = 1,
        @Query("page_size") pageSize: Int = 20,
    ): OrderListResponse

    /** 订单详情（仅参与方可见）。 */
    @GET("orders/{orderId}")
    suspend fun getOrder(@Path("orderId") orderId: String): Order

    /** 发起支付，返回 prepay 体（mock provider 下 mockSuccess=true 即成功）。 */
    @POST("orders/{orderId}/pay")
    suspend fun pay(@Path("orderId") orderId: String): PrepayResponse

    /** 取消订单，返回更新后订单。 */
    @POST("orders/{orderId}/cancel")
    suspend fun cancel(@Path("orderId") orderId: String): Order
}
