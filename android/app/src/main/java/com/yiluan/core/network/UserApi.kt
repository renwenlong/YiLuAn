package com.yiluan.core.network

import com.yiluan.core.model.SwitchRoleRequest
import com.yiluan.core.model.TokenResponse
import com.yiluan.core.model.UpdateMeRequest
import com.yiluan.core.model.User
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST

/**
 * 用户 API（需登录，走挂 AuthInterceptor 的业务 Retrofit）。
 * ANDROID-DEV-B1-AUTH — 当前用户信息 + 首次选角色 + 切换角色。
 *
 * 对齐 iOS AuthViewModel.setRole/switchRole：
 *  - updateMe(POST /users/me)：首次选角色，返回更新后 User，**不换 token**。
 *  - switchRole(POST /users/me/switch-role)：已登录切角色，返回 TokenResponse，
 *    **新 token 必须重存**（role claim 变了）。
 */
interface UserApi {
    /** 当前登录用户信息。 */
    @GET("users/me")
    suspend fun me(): User

    /**
     * 更新当前用户（首次选角色 / 改资料）。只传要改的字段。
     * 返回更新后的 User，不换 token。
     */
    @POST("users/me")
    suspend fun updateMe(@Body body: UpdateMeRequest): User

    /**
     * 切换活跃角色。⚠️ 返回新 token 对（role claim 更新），调用方必须重存 token。
     */
    @POST("users/me/switch-role")
    suspend fun switchRole(@Body body: SwitchRoleRequest): TokenResponse
}
