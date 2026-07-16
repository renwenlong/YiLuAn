package com.yiluan.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * 认证相关 DTO（对齐后端 auth endpoints + iOS AuthModels）。
 * ANDROID-DEV-B0-CORE — B0 只需 refresh 契约支撑 AuthInterceptor 401 刷新；
 * 完整登录 DTO（apple/wechat/otp）在 B1-AUTH 补齐。
 */

@Serializable
data class TokenPair(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("token_type") val tokenType: String = "bearer",
)

@Serializable
data class RefreshRequest(
    @SerialName("refresh_token") val refreshToken: String,
)
