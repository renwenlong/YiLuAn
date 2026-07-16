package com.yiluan.core.network

import com.yiluan.core.model.RefreshRequest
import com.yiluan.core.model.TokenPair
import retrofit2.http.Body
import retrofit2.http.POST

/**
 * 认证 API（token 刷新）。
 * ANDROID-DEV-B0-CORE — 独立于业务 ApiEndpoint，供 AuthInterceptor 401 刷新调用，
 * 走**不带 AuthInterceptor** 的裸 OkHttp，避免刷新请求自身触发 401 递归。
 */
interface AuthApi {
    @POST("auth/refresh")
    suspend fun refresh(@Body body: RefreshRequest): TokenPair
}
