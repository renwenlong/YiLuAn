package com.yiluan.core.share

import com.yiluan.core.model.CreateShareRequest
import com.yiluan.core.model.CreateShareResponse
import com.yiluan.core.model.ExchangeSessionRequest
import com.yiluan.core.model.ExchangeSessionResponse
import com.yiluan.core.model.OrderShareToken
import com.yiluan.core.model.ShareOrderResponse
import com.yiluan.core.model.ShareSendOtpRequest
import com.yiluan.core.model.ShareSendOtpResponse
import com.yiluan.core.network.ShareApi
import com.yiluan.core.network.WebSocketClient
import com.yiluan.core.realtime.ShareSocket
import com.yiluan.core.storage.ShareSessionStore
import kotlinx.coroutines.CoroutineScope
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Share 仓库：发起端(owner) + 接收端(访客 OTP/exchange/脱敏订单) + ShareSocket 工厂。
 * ANDROID-DEV-B5-PRECHECK-SHARE。
 *
 * 接收端 exchangeSession 成功后 share_session JWT 存 ShareSessionStore(加密, 30min TTL)；
 * 脱敏订单请求用该 session 走 Bearer header（AuthInterceptor 见已带 Authorization 放行）。
 */
@Singleton
class ShareRepository @Inject constructor(
    private val shareApi: ShareApi,
    private val wsClient: WebSocketClient,
    private val shareSessionStore: ShareSessionStore,
) {
    // ── 发起端 ──
    suspend fun createShare(orderId: String, scope: String): CreateShareResponse =
        shareApi.createShare(orderId, CreateShareRequest(shareScope = scope))

    suspend fun listShares(orderId: String): List<OrderShareToken> =
        shareApi.listShares(orderId).items

    suspend fun revokeShare(orderId: String, tokenId: String) =
        shareApi.revokeShare(orderId, tokenId)

    // ── 接收端 OTP ──
    suspend fun sendOtp(token: String, phone: String): ShareSendOtpResponse =
        shareApi.sendOtp(token, ShareSendOtpRequest(phone = phone))

    /** 验证 OTP 换 share_session，成功后存加密存储。 */
    suspend fun exchangeSession(token: String, phone: String, otp: String): ExchangeSessionResponse {
        val resp = shareApi.exchangeSession(token, ExchangeSessionRequest(phone = phone, otp = otp))
        val expiresMillis = parseExpiryMillis(resp.shareSessionExpiresAt)
        shareSessionStore.save(resp.shareSession, expiresMillis)
        return resp
    }

    /** 脱敏订单（用本地 share_session）；无 session/过期返回 null 让上层跳 OTP。 */
    suspend fun shareOrder(): ShareOrderResponse? {
        val session = shareSessionStore.session() ?: return null
        if (shareSessionStore.isExpired()) {
            shareSessionStore.clear()
            return null
        }
        return shareApi.shareSessionOrder("Bearer $session")
    }

    /** 当前 share_session（供 ShareSocket 握手）。 */
    fun currentSession(): String? =
        shareSessionStore.session()?.takeUnless { shareSessionStore.isExpired() }

    fun clearSession() = shareSessionStore.clear()

    fun createSocket(token: String, session: String, scope: CoroutineScope): ShareSocket =
        ShareSocket(token = token, shareSession = session, wsClient = wsClient, scope = scope)

    /** ISO8601 expires_at → epoch millis（解析失败给 30min 兜底）。 */
    private fun parseExpiryMillis(iso: String?): Long {
        if (iso == null) return System.currentTimeMillis() + 30 * 60 * 1000L
        return try {
            java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", java.util.Locale.US).apply {
                timeZone = java.util.TimeZone.getTimeZone("UTC")
            }.parse(iso.take(19))?.time ?: (System.currentTimeMillis() + 30 * 60 * 1000L)
        } catch (_: Exception) {
            System.currentTimeMillis() + 30 * 60 * 1000L
        }
    }
}
