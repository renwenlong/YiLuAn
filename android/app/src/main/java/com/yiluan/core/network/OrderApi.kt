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
 */
interface OrderApi {
    @POST("orders")
    suspend fun createOrder(@Body body: CreateOrderRequest): Order

    @GET("orders")
    suspend fun listOrders(
        @Query("status") status: String?,
        @Query("page") page: Int,
        @Query("page_size") pageSize: Int,
    ): OrderListResponse

    @GET("orders/{orderId}")
    suspend fun getOrder(@Path("orderId") orderId: String): Order

    @POST("orders/{orderId}/pay")
    suspend fun pay(@Path("orderId") orderId: String): PrepayResponse

    @POST("orders/{orderId}/cancel")
    suspend fun cancel(@Path("orderId") orderId: String): Order

    // ── B3 陪诊员 order action（均 POST /orders/{id}/{action}，无 body，返回更新后 Order）──

    /** 陪诊员接单: created→accepted（前置 PHONE_REQUIRED + VERIFICATION_REQUIRED）。 */
    @POST("orders/{orderId}/accept")
    suspend fun accept(@Path("orderId") orderId: String): Order

    /** 直接开始服务: accepted→in_progress。 */
    @POST("orders/{orderId}/start")
    suspend fun start(@Path("orderId") orderId: String): Order

    /** 陪诊员发起开始（待患者确认）。 */
    @POST("orders/{orderId}/request-start")
    suspend fun requestStart(@Path("orderId") orderId: String): Order

    /** 患者确认开始: →in_progress。 */
    @POST("orders/{orderId}/confirm-start")
    suspend fun confirmStart(@Path("orderId") orderId: String): Order

    /** 完成服务: in_progress→completed。 */
    @POST("orders/{orderId}/complete")
    suspend fun complete(@Path("orderId") orderId: String): Order

    /** 陪诊员拒单（仅 created 可拒）: created→rejected_by_companion。 */
    @POST("orders/{orderId}/reject")
    suspend fun reject(@Path("orderId") orderId: String): Order
}
