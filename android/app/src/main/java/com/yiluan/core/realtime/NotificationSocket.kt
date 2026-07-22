package com.yiluan.core.realtime

import com.yiluan.BuildConfig
import com.yiluan.core.model.Notification
import com.yiluan.core.model.WsAuthFrame
import com.yiluan.core.model.WsFrameEnvelope
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
 * Notification WS 封装（在 B0 WebSocketClient.WsConnection 之上）。
 * ANDROID-DEV-B4-REALTIME — WS 前台推 + 上层 REST 列表兜底。
 *
 * 分派：auth_ok(握手完成)/pong(心跳)/unread_count_changed(更新角标)/通知帧(插列表顶)。
 */
class NotificationSocket(
    private val wsClient: WebSocketClient,
    private val tokenStore: TokenStore,
    private val scope: CoroutineScope,
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val _events = MutableSharedFlow<NotificationSocketEvent>(extraBufferCapacity = 64)
    val events: SharedFlow<NotificationSocketEvent> = _events

    private var loopJob: Job? = null
    private var pingJob: Job? = null
    @Volatile private var conn: WebSocketClient.WsConnection? = null
    private var reconnectAttempt = 0

    private fun url(): String = "${BuildConfig.WS_BASE_URL}/notifications"

    fun connect() {
        if (loopJob?.isActive == true) return
        loopJob = scope.launch { runLoop() }
    }

    private suspend fun runLoop() {
        while (scope.isActive) {
            val token = tokenStore.accessToken() ?: return
            val connection = wsClient.openConnection(url(), pingIntervalSeconds = 0L)
            conn = connection
            val evJob = connection.events.onEach { ev ->
                when (ev) {
                    is WebSocketClient.WsEvent.Open -> {
                        connection.send(json.encodeToString(WsAuthFrame(token = token)))
                        startPing(connection)
                    }
                    is WebSocketClient.WsEvent.Message -> handleFrame(ev.text)
                    is WebSocketClient.WsEvent.Closed,
                    is WebSocketClient.WsEvent.Failure -> Unit
                }
            }.launchIn(scope)

            evJob.join()
            pingJob?.cancel()
            conn = null
            if (!scope.isActive) return
            reconnectAttempt++
            val backoff = minOf(30_000L, 1_000L * (1L shl minOf(reconnectAttempt, 5)))
            delay(backoff)
        }
    }

    private fun startPing(connection: WebSocketClient.WsConnection) {
        pingJob?.cancel()
        pingJob = scope.launch {
            while (scope.isActive) {
                delay(30_000L)
                connection.send(json.encodeToString(WsPingFrame()))
            }
        }
    }

    private fun handleFrame(text: String) {
        val env = try {
            json.decodeFromString<WsFrameEnvelope>(text)
        } catch (_: Exception) {
            return
        }
        when (env.type) {
            "auth_ok" -> reconnectAttempt = 0
            "pong" -> Unit
            "unread_count_changed" -> {
                env.count?.let { _events.tryEmit(NotificationSocketEvent.UnreadCount(it)) }
            }
            else -> {
                // 通知帧本体（type 是通知类型枚举）
                val n = try {
                    json.decodeFromString<Notification>(text)
                } catch (_: Exception) {
                    null
                }
                if (n != null) _events.tryEmit(NotificationSocketEvent.NewNotification(n))
            }
        }
    }

    fun disconnect() {
        pingJob?.cancel()
        loopJob?.cancel()
        conn?.close()
        conn = null
        loopJob = null
    }
}

/** Notification WS 事件。 */
sealed interface NotificationSocketEvent {
    data class NewNotification(val notification: Notification) : NotificationSocketEvent
    data class UnreadCount(val count: Int) : NotificationSocketEvent
}
