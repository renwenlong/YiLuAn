package com.yiluan.core.network

import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.util.concurrent.TimeUnit
import javax.inject.Inject
import javax.inject.Singleton

/**
 * WebSocket 基座（OkHttp WS）。
 * ANDROID-DEV-B0-CORE — 对齐 iOS/小程序 ws-base 语义（JWT query 认证 + 心跳 ping）。
 *
 * 设计（对齐 design §3.2/§3.3）：
 *  - 认证：JWT 走 query 参数（后端 ws.py 语义）；家属 share_session 流由调用方拼 url。
 *  - 心跳：OkHttp `pingInterval` 自动发 ping（默认 20s），维持连接。
 *  - 事件以 Flow<WsEvent> 暴露，调用方 collect；断线/失败由 Closed/Failure 事件透出，
 *    重连/轮询兜底策略由上层 Feature ViewModel 决定（B4/B5 落地，design 已定阈值）。
 *  - 复用注入的 OkHttpClient 实例（与 REST 同栈，避免双栈）。
 */
@Singleton
class WebSocketClient @Inject constructor(
    private val baseClient: OkHttpClient,
) {
    /** WS 生命周期事件。 */
    sealed interface WsEvent {
        data object Open : WsEvent
        data class Message(val text: String) : WsEvent
        data class Closed(val code: Int, val reason: String) : WsEvent
        data class Failure(val error: Throwable) : WsEvent
    }

    /**
     * 建立 WS 连接，返回事件流。collect 取消时自动关闭连接。
     * @param url 完整 wss url（含 query 认证参数）。
     * @param pingIntervalSeconds 心跳间隔，默认 20s（对齐 ws-base）。
     */
    fun connect(url: String, pingIntervalSeconds: Long = 20L): Flow<WsEvent> = callbackFlow {
        val client = baseClient.newBuilder()
            .pingInterval(pingIntervalSeconds, TimeUnit.SECONDS)
            .build()

        val request = Request.Builder().url(url).build()
        val listener = object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                trySend(WsEvent.Open)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                trySend(WsEvent.Message(text))
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                webSocket.close(code, reason)
            }

            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                trySend(WsEvent.Closed(code, reason))
                channel.close()
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                trySend(WsEvent.Failure(t))
                channel.close(t)
            }
        }

        val ws = client.newWebSocket(request, listener)
        awaitClose { ws.close(1000, "client closed") }
    }
}
