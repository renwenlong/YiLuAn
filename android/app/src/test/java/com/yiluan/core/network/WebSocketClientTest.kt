package com.yiluan.core.network

import app.cash.turbine.test
import kotlinx.coroutines.runBlocking
import okhttp3.OkHttpClient
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * WebSocketClient 单测（ANDROID-BUG-B0-TEST-COVERAGE-GAP AC3: WS 建连+心跳）。
 * 用 MockWebServer 的 WebSocket upgrade 驱动真实 OkHttp WS，验：
 *  - connect → Open 事件
 *  - 服务端下发消息 → Message 事件
 *  - 服务端关闭 → Closed 事件 + Flow 结束
 *  - pingInterval 配置生效（心跳参数传入 OkHttp，不崩）
 */
class WebSocketClientTest {

    private lateinit var server: MockWebServer
    private lateinit var client: WebSocketClient

    @Before
    fun setup() {
        server = MockWebServer()
        server.start()
        client = WebSocketClient(OkHttpClient())
    }

    @After
    fun teardown() {
        // MockWebServer 在仍有活跃 WS 连接时 shutdown() 会抛 IOException
        // ("Gave up waiting for ... to shut down")。测试主体已在 test{} block 内
        // 验证完毕并 cancel, 清理阶段的 shutdown 异常不应判定用例失败, 吞掉即可。
        try {
            server.shutdown()
        } catch (_: Exception) {
            // 清理阶段忽略: 连接关闭与 shutdown 的竞速属预期, 不影响断言结果
        }
    }

    private fun wsUrl(): String =
        server.url("/ws").toString().replaceFirst("http", "ws")

    @Test
    fun `建连触发 Open 事件`() = runBlocking {
        server.enqueue(MockResponse().withWebSocketUpgrade(object : okhttp3.WebSocketListener() {}))

        client.connect(wsUrl()).test {
            assertEquals(WebSocketClient.WsEvent.Open, awaitItem())
            cancelAndConsumeRemainingEvents()
        }
    }

    @Test
    fun `服务端下发消息触发 Message 事件`() = runBlocking {
        server.enqueue(
            MockResponse().withWebSocketUpgrade(object : okhttp3.WebSocketListener() {
                override fun onOpen(webSocket: okhttp3.WebSocket, response: okhttp3.Response) {
                    webSocket.send("hello")
                }
            })
        )

        client.connect(wsUrl()).test {
            assertEquals(WebSocketClient.WsEvent.Open, awaitItem())
            val msg = awaitItem()
            assertTrue(msg is WebSocketClient.WsEvent.Message)
            assertEquals("hello", (msg as WebSocketClient.WsEvent.Message).text)
            cancelAndConsumeRemainingEvents()
        }
    }

    @Test
    fun `服务端关闭触发 Closed 事件并结束 Flow`() = runBlocking {
        server.enqueue(
            MockResponse().withWebSocketUpgrade(object : okhttp3.WebSocketListener() {
                override fun onOpen(webSocket: okhttp3.WebSocket, response: okhttp3.Response) {
                    webSocket.close(1000, "bye")
                }
            })
        )

        client.connect(wsUrl()).test {
            // Open 可能先到，也可能被 close 竞速；消费直到 Closed。
            var sawClosed = false
            while (!sawClosed) {
                val ev = awaitItem()
                if (ev is WebSocketClient.WsEvent.Closed) {
                    assertEquals(1000, ev.code)
                    sawClosed = true
                }
            }
            awaitComplete()
        }
    }

    @Test
    fun `自定义心跳间隔不影响建连`() = runBlocking {
        server.enqueue(MockResponse().withWebSocketUpgrade(object : okhttp3.WebSocketListener() {}))

        // pingInterval=1s，验证参数传入不崩且能正常建连（心跳由 OkHttp 内部驱动）。
        client.connect(wsUrl(), pingIntervalSeconds = 1L).test {
            assertEquals(WebSocketClient.WsEvent.Open, awaitItem())
            cancelAndConsumeRemainingEvents()
        }
    }
}
