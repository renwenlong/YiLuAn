package com.yiluan.core.model

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/**
 * 认证相关 DTO（对齐后端 auth endpoints + iOS AuthModels）。
 * ANDROID-DEV-B0-CORE — B0 只需 refresh 契约支撑 AuthInterceptor 401 刷新。
 * ANDROID-DEV-B1-AUTH — 补齐手机 OTP 登录 + role-select 完整 DTO。
 *
 * 约定：全部 body/response 走 snake_case，显式 @SerialName 映射（不依赖全局策略）。
 */

// MARK: - Token

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

// MARK: - OTP 登录

@Serializable
data class SendOtpRequest(
    @SerialName("phone") val phone: String,
)

@Serializable
data class SendOtpResponse(
    @SerialName("message") val message: String? = null,
)

@Serializable
data class VerifyOtpRequest(
    @SerialName("phone") val phone: String,
    @SerialName("code") val code: String,
)

/**
 * 登录/验证成功响应：token 对 + 用户信息。
 * verify-otp 未注册手机号会自动注册新用户（新用户 role=null）。
 */
@Serializable
data class TokenResponse(
    @SerialName("access_token") val accessToken: String,
    @SerialName("refresh_token") val refreshToken: String,
    @SerialName("user") val user: User,
)

// MARK: - 用户 + 角色

@Serializable
data class User(
    @SerialName("id") val id: String,
    @SerialName("phone") val phone: String? = null,
    /** 当前活跃角色（可为 null，未选角色时）。 */
    @SerialName("role") val role: String? = null,
    /** 已开通角色集合。 */
    @SerialName("roles") val roles: List<String> = emptyList(),
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
    @SerialName("created_at") val createdAt: String? = null,
)

/**
 * 首次选角色（POST /users/me，不换 token）+ 更新资料共用。
 * role/displayName/avatarUrl 均可选，只传要改的字段。
 */
@Serializable
data class UpdateMeRequest(
    @SerialName("role") val role: String? = null,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("avatar_url") val avatarUrl: String? = null,
)

/**
 * 已登录切换角色（POST /users/me/switch-role）。
 * ⚠️ 返回 TokenResponse（新 token，role claim 更新），必须重存 token。
 */
@Serializable
data class SwitchRoleRequest(
    @SerialName("role") val role: String,
)

/**
 * 用户角色枚举（对齐 iOS UserRole，后端严格校验只接受这两个字符串值）。
 */
enum class UserRole(val value: String) {
    PATIENT("patient"),
    COMPANION("companion");

    companion object {
        fun fromValue(v: String?): UserRole? = entries.firstOrNull { it.value == v }
    }
}
