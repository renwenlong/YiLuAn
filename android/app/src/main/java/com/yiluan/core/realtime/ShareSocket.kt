package com.yiluan.core.realtime

import com.yiluan.BuildConfig
import com.yiluan.core.model.ShareAuthFrame
import com.yiluan.core.model.ShareWsFrame
import com.yiluan.core.network.WebSocketClient
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * Share 接收端 WS 封装（访客侧，在 WsConnection 之上）。
 * ANDROID-DEV-B5-PRECHECK-SHARE。
 *
 * 关键契约（与 Precheck WS 不同）：
 *  - WS 路径 /api/v1/ws/share/{token}（带 /api/v1，用 WS_BASE_URL）。
 *  - first-frame {type:share_auth, session:<share_session_jwt>} → share_auth_ok/share_auth_err。
 *  - 心跳用 WS protocol ping（OkHttp pingInterval，非应用层 JSON ping）。
 *  - 只读；不内置重连（4013/4001 跳回 OTP；4014/4012/抖动上层可重连 1-2 次）。
 */
class ShareSocket(
    private val token: String,
    private val shareSession: String,
    private val wsClient: WebSocketClient,
    private val scope: CoroutineScope,
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val _events = MutableSharedFlow<ShareSocketEvent>(extraBufferCapacity = 32)
    val events: SharedFlow<ShareSocketEvent> = _events

    private var evJob: Job? = null
    @Volatile private var conn: WebSocketClient.WsConnection? = null

    private fun url(): String = "${BuildConfig.WS_BASE_URL}/share/$token"

    fun connect() {
        if (evJob?.isActive == true) return
        // protocol ping：pingIntervalSeconds=30 让 OkHttp 发原生 ping 帧。
        val connection = wsClient.openConnection(url(), pingIntervalSeconds = 30L)
        conn = connection
        evJob = connection.events.onEach { ev ->
            when (ev) {
                is WebSocketClient.WsEvent.Open -> {
                    connection.send(json.encodeToString(ShareAuthFrame(session = shareSession)))
                }
                is WebSocketClient.WsEvent.Message -> handleFrame(ev.text)
                is WebSocketClient.WsEvent.Closed -> handleClose(ev.code)
                is WebSocketClient.WsEvent.Failure -> _events.tryEmit(ShareSocketEvent.Disconnected(null))
            }
        }.launchIn(scope)
    }

    private fun handleFrame(text: String) {
        val frame = try {
            json.decodeFromString<ShareWsFrame>(text)
        } catch (_: Exception) {
            return
        }
        when (frame.type) {
            "share_auth_ok" -> _events.tryEmit(ShareSocketEvent.Authed)
            "share_auth_err" -> _events.tryEmit(ShareSocketEvent.AuthError(frame.reason))
            else -> frame.event?.let { _events.tryEmit(ShareSocketEvent.Update(it)) }
        }
    }

    private fun handleClose(code: Int) {
        // 4013 token 撤销/过期 / 4001 token 不匹配 → 上层跳回 OTP;
        // 4014 超并发 / 4012 write / 其他抖动 → 上层可重连。
        when (code) {
            4013, 4001 -> _events.tryEmit(ShareSocketEvent.Revoked(code))
            else -> _events.tryEmit(ShareSocketEvent.Disconnected(code))
        }
    }

    fun disconnect() {
        evJob?.cancel()
        conn?.close()
        conn = null
        evJob = null
    }
}

/** Share 接收端 WS 事件。 */
sealed interface ShareSocketEvent {
    data object Authed : ShareSocketEvent
    data class AuthError(val reason: String?) : ShareSocketEvent
    /** 业务更新事件 → 上层重拉脱敏订单。 */
    data class Update(val event: String) : ShareSocketEvent
    /** token 撤销/过期(4013/4001) → 上层跳回 OTP。 */
    data class Revoked(val closeCode: Int) : ShareSocketEvent
    /** 抖动断开(可重连) → 上层决策。 */
    data class Disconnected(val closeCode: Int?) : ShareSocketEvent
}
