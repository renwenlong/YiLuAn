package com.yiluan.core.realtime

import com.yiluan.BuildConfig
import com.yiluan.core.model.PrecheckWsFrame
import com.yiluan.core.model.WsAuthFrame
import com.yiluan.core.model.WsPingFrame
import com.yiluan.core.network.WebSocketClient
import com.yiluan.core.storage.TokenStore
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.SharedFlow
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

/**
 * Precheck WS 封装（在 B0 WebSocketClient.WsConnection 之上）。
 * ANDROID-DEV-B5-PRECHECK-SHARE。
 *
 * 关键契约（勿照抄 B4/iOS）：
 *  - WS 路径 /ws/v1/orders/{id}/precheck（无 /api 前缀，从 WS_BASE_URL 推导）。
 *  - first-frame auth + 应用层 JSON ping（非 protocol ping，后端只读 JSON 帧）。
 *  - 只读流：event 帧(precheck.status.updated/all_ready/blocked) 仅 invalidate 信号 →
 *    发 Invalidated 事件让上层重拉 HTTP summary（payload 不含完整数据）。
 *  - auth 超时(5s 未 auth_ok) 或永久 close → 发 NeedPolling 让上层切轮询(3s×10)。
 *  - 不内置激进重连（避免与轮询兜底打架，重连交上层按 close code 决策）。
 */
class PrecheckSocket(
    private val orderId: String,
    private val wsClient: WebSocketClient,
    private val tokenStore: TokenStore,
    private val scope: CoroutineScope,
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val _events = MutableSharedFlow<PrecheckSocketEvent>(extraBufferCapacity = 32)
    val events: SharedFlow<PrecheckSocketEvent> = _events

    private var connJob: Job? = null
    private var pingJob: Job? = null
    private var authTimeoutJob: Job? = null
    @Volatile private var conn: WebSocketClient.WsConnection? = null
    @Volatile private var authed = false

    /** Precheck WS url：WS_BASE_URL(.../api/v1/ws) → .../ws/v1/orders/{id}/precheck。 */
    private fun url(): String {
        val base = BuildConfig.WS_BASE_URL.replace("/api/v1/ws", "/ws/v1")
        return "$base/orders/$orderId/precheck"
    }

    fun connect() {
        if (connJob?.isActive == true) return
        authed = false
        connJob = scope.launch { run() }
    }

    private suspend fun run() {
        val token = tokenStore.accessToken() ?: run {
            _events.tryEmit(PrecheckSocketEvent.NeedPolling)
            return
        }
        val connection = wsClient.openConnection(url(), pingIntervalSeconds = 0L)
        conn = connection

        // 5s auth 超时 → 切轮询
        authTimeoutJob = scope.launch {
            delay(5_000L)
            if (!authed) _events.tryEmit(PrecheckSocketEvent.NeedPolling)
        }

        connection.events.onEach { ev ->
            when (ev) {
                is WebSocketClient.WsEvent.Open -> {
                    connection.send(json.encodeToString(WsAuthFrame(token = token)))
                }
                is WebSocketClient.WsEvent.Message -> handleFrame(ev.text)
                is WebSocketClient.WsEvent.Closed -> handleClose((ev).code)
                is WebSocketClient.WsEvent.Failure -> _events.tryEmit(PrecheckSocketEvent.NeedPolling)
            }
        }.launchIn(scope)
    }

    private fun handleFrame(text: String) {
        val frame = try {
            json.decodeFromString<PrecheckWsFrame>(text)
        } catch (_: Exception) {
            return
        }
        when {
            frame.type == "auth_ok" -> {
                authed = true
                authTimeoutJob?.cancel()
                _events.tryEmit(PrecheckSocketEvent.Connected) // 上层停轮询
                startPing()
            }
            frame.type == "pong" -> Unit
            frame.event != null -> {
                // precheck.status.updated / all_ready / blocked → invalidate 信号
                _events.tryEmit(PrecheckSocketEvent.Invalidated(frame.event))
            }
        }
    }

    private fun handleClose(code: Int) {
        pingJob?.cancel()
        // 永久失败(4001 auth/4003 not_owner/4004 not_found/4011 auth_timeout) → 报错不轮询;
        // 临时(4002 idle/其他) → 轮询兜底。
        when (code) {
            4001, 4003, 4004, 4011 -> _events.tryEmit(PrecheckSocketEvent.Error(code))
            else -> _events.tryEmit(PrecheckSocketEvent.NeedPolling)
        }
    }

    private fun startPing() {
        pingJob?.cancel()
        pingJob = scope.launch {
            while (scope.isActive) {
                delay(30_000L)
                conn?.send(json.encodeToString(WsPingFrame()))
            }
        }
    }

    fun disconnect() {
        authTimeoutJob?.cancel()
        pingJob?.cancel()
        connJob?.cancel()
        conn?.close()
        conn = null
        connJob = null
    }
}

/** Precheck WS 事件。 */
sealed interface PrecheckSocketEvent {
    /** auth_ok，WS 就绪 → 上层停轮询。 */
    data object Connected : PrecheckSocketEvent
    /** 收到 event 推送 → 上层重拉 HTTP summary。 */
    data class Invalidated(val event: String) : PrecheckSocketEvent
    /** auth 超时/临时失败 → 上层切轮询(3s×10)。 */
    data object NeedPolling : PrecheckSocketEvent
    /** 永久失败(close code) → 上层报错。 */
    data class Error(val closeCode: Int) : PrecheckSocketEvent
}
