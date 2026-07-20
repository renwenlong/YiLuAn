package com.yiluan.core.realtime

import com.yiluan.BuildConfig
import com.yiluan.core.model.ChatMessage
import com.yiluan.core.model.WsAuthFrame
import com.yiluan.core.model.WsFrameEnvelope
import com.yiluan.core.model.WsPingFrame
import com.yiluan.core.model.WsSendMessageFrame
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
import java.util.UUID

/**
 * Chat WS 封装（在 B0 WebSocketClient.WsConnection 之上）。
 * ANDROID-DEV-B4-REALTIME — 一订单一会话。
 *
 * 职责：first-frame auth 握手 + 帧按 type 分派(过滤 auth_ok/pong 控制帧) +
 *      app 层 JSON ping 心跳(30s, server 90s idle) + 断线指数退避重连 + 重连触发 backfill(AC3)。
 *
 * 事件以 ChatSocketEvent Flow 暴露；backfill 补偿由上层 Repository 在收到 Reconnected 时做。
 */
class ChatSocket(
    private val orderId: String,
    private val wsClient: WebSocketClient,
    private val tokenStore: TokenStore,
    private val scope: CoroutineScope,
) {
    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }
    private val _events = MutableSharedFlow<ChatSocketEvent>(extraBufferCapacity = 64)
    val events: SharedFlow<ChatSocketEvent> = _events

    private var loopJob: Job? = null
    private var pingJob: Job? = null
    @Volatile private var conn: WebSocketClient.WsConnection? = null
    private var reconnectAttempt = 0
    private var everConnected = false

    private fun url(): String = "${BuildConfig.WS_BASE_URL}/chat/$orderId"

    fun connect() {
        if (loopJob?.isActive == true) return
        loopJob = scope.launch { runLoop() }
    }

    private suspend fun runLoop() {
        while (scope.isActive) {
            val token = tokenStore.accessToken() ?: run {
                _events.tryEmit(ChatSocketEvent.Closed)
                return
            }
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
                    is WebSocketClient.WsEvent.Failure -> Unit // 循环外统一处理重连
                }
            }.launchIn(scope)

            evJob.join() // flow 结束 = 连接关闭
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
            "auth_ok" -> {
                if (everConnected) _events.tryEmit(ChatSocketEvent.Reconnected)
                everConnected = true
                reconnectAttempt = 0
            }
            "pong" -> Unit
            "text", "image", "system" -> {
                val msg = try {
                    json.decodeFromString<ChatMessage>(text)
                } catch (_: Exception) {
                    null
                }
                if (msg != null) _events.tryEmit(ChatSocketEvent.Message(msg))
            }
            else -> Unit
        }
    }

    /** WS 发消息（nonce 幂等）；未连上返回 false，上层降级 REST。 */
    fun sendMessage(type: String, content: String): Boolean {
        val c = conn ?: return false
        return c.send(
            json.encodeToString(
                WsSendMessageFrame(type = type, content = content, nonce = UUID.randomUUID().toString()),
            ),
        )
    }

    fun disconnect() {
        pingJob?.cancel()
        loopJob?.cancel()
        conn?.close()
        conn = null
        loopJob = null
    }
}

/** Chat WS 事件。 */
sealed interface ChatSocketEvent {
    data class Message(val message: ChatMessage) : ChatSocketEvent
    /** 重连成功 → 上层走 backfill 补偿(AC3)。 */
    data object Reconnected : ChatSocketEvent
    data object Closed : ChatSocketEvent
}
