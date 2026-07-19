package com.yiluan.core.network

import com.yiluan.core.model.RefreshRequest
import com.yiluan.core.model.SendOtpRequest
import com.yiluan.core.model.SendOtpResponse
import com.yiluan.core.model.TokenPair
import com.yiluan.core.model.TokenResponse
import com.yiluan.core.model.VerifyOtpRequest
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * 认证 API（登录 + token 刷新）。
 * ANDROID-DEV-B0-CORE — refresh 契约支撑 AuthInterceptor 401 刷新。
 * ANDROID-DEV-B1-AUTH — 补齐手机 OTP 登录。
 *
 * 走**不带 AuthInterceptor** 的裸 OkHttp：
 *  - refresh：避免刷新请求自身触发 401 递归。
 *  - send-otp/verify-otp：登录前无 token，本就无需 auth。
 */
interface AuthApi {
    @POST("auth/refresh")
    suspend fun refresh(@Body body: RefreshRequest): TokenPair

    /** 发送手机验证码（限流 5/min）。 */
    @POST("auth/send-otp")
    suspend fun sendOtp(@Body body: SendOtpRequest): SendOtpResponse

    /**
     * 验证 OTP 登录（限流 10/min）。
     * 未注册手机号自动注册新用户（新用户 role=null）。
     */
    @POST("auth/verify-otp")
    suspend fun verifyOtp(@Body body: VerifyOtpRequest): TokenResponse
}
