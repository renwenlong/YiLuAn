package com.yiluan.core.auth

import com.yiluan.core.model.SendOtpRequest
import com.yiluan.core.model.SwitchRoleRequest
import com.yiluan.core.model.TokenResponse
import com.yiluan.core.model.UpdateMeRequest
import com.yiluan.core.model.User
import com.yiluan.core.model.VerifyOtpRequest
import com.yiluan.core.network.AuthApi
import com.yiluan.core.network.UserApi
import com.yiluan.core.storage.TokenStore
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 认证仓库：封装登录 / token 存储 / role 逻辑，供 ViewModel 调用。
 * ANDROID-DEV-B1-AUTH — 对齐 iOS AuthViewModel 的后端交互序列。
 *
 * 职责边界：
 *  - 只做数据编排（调 API + 存 token），不持 UI 状态（UI 状态在 ViewModel）。
 *  - token 落 TokenStore（AuthInterceptor 从此读，后续请求自动带 auth）。
 */
@Singleton
class AuthRepository @Inject constructor(
    private val authApi: AuthApi,
    private val userApi: UserApi,
    private val tokenStore: TokenStore,
) {
    /** 发送手机验证码。 */
    suspend fun sendOtp(phone: String) {
        authApi.sendOtp(SendOtpRequest(phone = phone))
    }

    /**
     * 验证 OTP 登录：成功后存 token，返回 user。
     * 未注册手机号后端自动注册（新用户 role=null → 上层引导选角色）。
     */
    suspend fun verifyOtp(phone: String, code: String): User {
        val resp = authApi.verifyOtp(VerifyOtpRequest(phone = phone, code = code))
        tokenStore.saveTokens(resp.accessToken, resp.refreshToken)
        return resp.user
    }

    /**
     * 首次选角色：POST /users/me，不换 token，返回更新后 User。
     */
    suspend fun setRole(role: String): User {
        return userApi.updateMe(UpdateMeRequest(role = role))
    }

    /**
     * 首次登录资料初始化：POST /users/me 设 display_name，不换 token，返回更新后 User。
     * ANDROID-DEV-GAP-PROFILE-SETUP — 对齐 iOS ProfileSetupView 昵称初始化。
     */
    suspend fun updateProfile(displayName: String): User {
        return userApi.updateMe(UpdateMeRequest(displayName = displayName))
    }

    /**
     * 已登录切换角色：POST /users/me/switch-role，返回新 token 对（必须重存）。
     */
    suspend fun switchRole(role: String): User {
        val resp: TokenResponse = userApi.switchRole(SwitchRoleRequest(role = role))
        tokenStore.saveTokens(resp.accessToken, resp.refreshToken)
        return resp.user
    }

    /** 拉当前用户信息（已登录）。 */
    suspend fun currentUser(): User = userApi.me()

    /** 是否已有本地 token（用于启动时判断登录态）。 */
    suspend fun hasToken(): Boolean = tokenStore.accessToken() != null

    /** 登出：清本地 token。 */
    suspend fun logout() {
        tokenStore.clear()
    }
}
