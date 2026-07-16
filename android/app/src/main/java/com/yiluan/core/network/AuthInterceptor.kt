package com.yiluan.core.network

import com.yiluan.core.model.RefreshRequest
import com.yiluan.core.storage.TokenStore
import kotlinx.coroutines.runBlocking
import okhttp3.Interceptor
import okhttp3.Response
import java.net.HttpURLConnection
import javax.inject.Inject
import javax.inject.Provider
import javax.inject.Singleton

/**
 * 认证拦截器：注入 Authorization + 401 自动 refresh。
 * ANDROID-DEV-B0-CORE (AC: 401 自动 refresh token) — 对齐 iOS APIClient 刷新语义。
 *
 * 流程：
 *  1. 无 access token 或请求已带 Authorization（如 share_session 路径）→ 原样放行。
 *  2. 注入本人 access token 发请求。
 *  3. 若 401 → 用 refresh token 换新 token（走 AuthApi，无本拦截器，防递归）→
 *     成功则用新 access token 重放一次原请求；刷新失败 → 清 token，返回原 401。
 *
 * 并发保护：refresh 用同步锁串行化，避免多请求同时 401 触发多次刷新。
 * AuthApi 用 Provider 延迟取，打破 Retrofit ↔ OkHttp ↔ Interceptor 的构造环。
 */
@Singleton
class AuthInterceptor @Inject constructor(
    private val tokenStore: TokenStore,
    private val authApiProvider: Provider<AuthApi>,
) : Interceptor {

    private val refreshLock = Any()

    override fun intercept(chain: Interceptor.Chain): Response {
        val original = chain.request()

        // 已显式带 Authorization（如家属 share_session 流）→ 不覆盖，直接放行。
        if (original.header("Authorization") != null) {
            return chain.proceed(original)
        }

        val access = runBlocking { tokenStore.accessToken() }
            ?: return chain.proceed(original) // 未登录态，放行由后端决定

        val authed = original.newBuilder()
            .header("Authorization", "Bearer $access")
            .build()
        val response = chain.proceed(authed)

        if (response.code != HttpURLConnection.HTTP_UNAUTHORIZED) {
            return response
        }

        // 401 → 尝试刷新（串行）。
        val newAccess = synchronized(refreshLock) {
            val current = runBlocking { tokenStore.accessToken() }
            // 双检：若刷新期间别的请求已刷新过（token 变了），直接用新值重放。
            if (current != null && current != access) {
                current
            } else {
                runBlocking { tryRefresh() }
            }
        } ?: return response // 刷新失败，返回原 401（response 未被消费重放）

        response.close()
        val retried = original.newBuilder()
            .header("Authorization", "Bearer $newAccess")
            .build()
        return chain.proceed(retried)
    }

    private suspend fun tryRefresh(): String? {
        val refresh = tokenStore.refreshToken() ?: return null
        return try {
            val pair = authApiProvider.get().refresh(RefreshRequest(refresh))
            tokenStore.saveTokens(pair.accessToken, pair.refreshToken)
            pair.accessToken
        } catch (e: Exception) {
            tokenStore.clear()
            null
        }
    }
}
