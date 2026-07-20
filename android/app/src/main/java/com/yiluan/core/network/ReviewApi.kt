package com.yiluan.core.network

import com.yiluan.core.model.CreateReviewRequest
import com.yiluan.core.model.ReviewResponse
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * 评价 API（需登录）。ANDROID-DEV-B6-LONGTAIL。
 * ⚠️ 提交评价驱动订单 completed→reviewed（业务功能，与订单状态机联动）。
 * 前置: 仅 patient 本人、订单须 completed、单订单一次。
 */
interface ReviewApi {
    @POST("orders/{orderId}/review")
    suspend fun submit(
        @Path("orderId") orderId: String,
        @Body body: CreateReviewRequest,
    ): ReviewResponse

    @GET("orders/{orderId}/review")
    suspend fun getReview(@Path("orderId") orderId: String): ReviewResponse
}
