package com.yiluan.feature.chat

import com.yiluan.core.model.ChatMessage
import com.yiluan.core.realtime.ChatRepository
import com.yiluan.core.realtime.ChatSocket
import com.yiluan.core.realtime.ChatSocketEvent
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import io.mockk.coVerify
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * ChatViewModel 单测（ANDROID-DEV-B4-REALTIME）。
 * 覆盖: 首屏历史 / WS 新消息去重追加 / 重连 backfill(AC3) / 发送 WS 主 REST 兜底。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ChatViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var repo: ChatRepository
    private lateinit var socket: ChatSocket
    private lateinit var events: MutableSharedFlow<ChatSocketEvent>
    private lateinit var vm: ChatViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        repo = mockk(relaxed = true)
        socket = mockk(relaxed = true)
        events = MutableSharedFlow(extraBufferCapacity = 16)
        every { socket.events } returns events
        every { repo.createSocket(any(), any()) } returns socket
        vm = ChatViewModel(repo)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    private fun msg(id: String, at: String) = ChatMessage(
        id = id, orderId = "o1", senderId = "u1", content = "hi $id", createdAt = at,
    )

    @Test
    fun `进入拉首屏历史并标已读`() = runTest(dispatcher) {
        coEvery { repo.history("o1") } returns listOf(msg("m1", "2026-08-01T10:00:00Z"))
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.messages.size)
        coVerify { repo.markRead("o1") }
    }

    @Test
    fun `WS 新消息去重追加`() = runTest(dispatcher) {
        coEvery { repo.history("o1") } returns emptyList()
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        events.emit(ChatSocketEvent.Message(msg("m1", "2026-08-01T10:00:00Z")))
        events.emit(ChatSocketEvent.Message(msg("m1", "2026-08-01T10:00:00Z"))) // 重复
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.messages.size) // 去重
        assertTrue(vm.uiState.value.connected)
    }

    @Test
    fun `重连触发 backfill 补齐漏消息`() = runTest(dispatcher) {
        coEvery { repo.history("o1") } returns listOf(msg("m1", "2026-08-01T10:00:00Z"))
        coEvery { repo.backfill("o1", afterId = "m1") } returns
            listOf(msg("m2", "2026-08-01T10:01:00Z"), msg("m3", "2026-08-01T10:02:00Z"))
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        events.emit(ChatSocketEvent.Reconnected)
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(3, vm.uiState.value.messages.size) // m1 + backfill m2/m3
        coVerify { repo.backfill("o1", afterId = "m1") }
    }

    @Test
    fun `发送 WS 成功不走 REST`() = runTest(dispatcher) {
        coEvery { repo.history("o1") } returns emptyList()
        every { socket.sendMessage("text", "hello") } returns true
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        vm.onInputChange("hello")
        vm.send()
        dispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 0) { repo.sendViaRest(any(), any(), any()) }
        assertEquals("", vm.uiState.value.input)
    }

    @Test
    fun `发送 WS 失败降级 REST`() = runTest(dispatcher) {
        coEvery { repo.history("o1") } returns emptyList()
        every { socket.sendMessage("text", "hello") } returns false
        coEvery { repo.sendViaRest("o1", "hello", "text") } returns msg("m9", "2026-08-01T10:05:00Z")
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        vm.onInputChange("hello")
        vm.send()
        dispatcher.scheduler.advanceUntilIdle()
        coVerify { repo.sendViaRest("o1", "hello", "text") }
        assertEquals(1, vm.uiState.value.messages.size)
    }

    @Test
    fun `空输入不发送`() = runTest(dispatcher) {
        coEvery { repo.history("o1") } returns emptyList()
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        vm.onInputChange("   ")
        vm.send()
        dispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = 0) { repo.sendViaRest(any(), any(), any()) }
    }
}
