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
}
