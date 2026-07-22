package com.yiluan.core.network

import com.yiluan.core.model.CreateShareRequest
import com.yiluan.core.model.CreateShareResponse
import com.yiluan.core.model.ExchangeSessionRequest
import com.yiluan.core.model.ExchangeSessionResponse
import com.yiluan.core.model.ListSharesResponse
import com.yiluan.core.model.ShareOrderResponse
import com.yiluan.core.model.ShareSendOtpRequest
import com.yiluan.core.model.ShareSendOtpResponse
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.Header
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * Share API（发起端 + 接收端）。ANDROID-DEV-B5-PRECHECK-SHARE。
 *
 * - 发起端(createShare/listShares/revokeShare): 需 access_token, AuthInterceptor 自动带。
 * - 接收端 OTP(sendOtp/exchangeSession): requires_auth=false, 未登录访客; AuthInterceptor
 *   无 token 时放行, 显式无 Authorization。
 * - 接收端脱敏订单(shareSessionOrder): 用 share_session JWT 走 @Header("Authorization"),
 *   AuthInterceptor 检测已带 Authorization → 原样放行不覆盖(B0 设计)。
 */
interface ShareApi {
    // ── 发起端（authed）──
    @POST("orders/{orderId}/shares")
    suspend fun createShare(
        @Path("orderId") orderId: String,
        @Body body: CreateShareRequest,
    ): CreateShareResponse

    @GET("orders/{orderId}/shares")
    suspend fun listShares(@Path("orderId") orderId: String): ListSharesResponse

    @DELETE("orders/{orderId}/shares/{tokenId}")
    suspend fun revokeShare(
        @Path("orderId") orderId: String,
        @Path("tokenId") tokenId: String,
    )

    // ── 接收端 OTP（无需登录）──
    @POST("shares/{token}/otp")
    suspend fun sendOtp(
        @Path("token") token: String,
        @Body body: ShareSendOtpRequest,
    ): ShareSendOtpResponse

    @POST("shares/{token}/session")
    suspend fun exchangeSession(
        @Path("token") token: String,
        @Body body: ExchangeSessionRequest,
    ): ExchangeSessionResponse

    // ── 接收端脱敏订单（share_session header）──
    @GET("shares/session/order")
    suspend fun shareSessionOrder(
        @Header("Authorization") shareSessionBearer: String,
    ): ShareOrderResponse
}
