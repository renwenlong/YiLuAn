package com.yiluan.feature.notification

import com.yiluan.core.model.Notification
import com.yiluan.core.realtime.NotificationRepository
import com.yiluan.core.realtime.NotificationSocket
import com.yiluan.core.realtime.NotificationSocketEvent
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.every
import io.mockk.mockk
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
 * NotificationViewModel 单测（ANDROID-DEV-B4-REALTIME）。
 * 覆盖: 列表+未读数加载 / WS 新通知去重插顶 / unread_count_changed / 标已读 / 全部已读。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class NotificationViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var repo: NotificationRepository
    private lateinit var socket: NotificationSocket
    private lateinit var events: MutableSharedFlow<NotificationSocketEvent>
    private lateinit var vm: NotificationViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        repo = mockk(relaxed = true)
        socket = mockk(relaxed = true)
        events = MutableSharedFlow(extraBufferCapacity = 16)
        every { socket.events } returns events
        every { repo.createSocket(any()) } returns socket
        vm = NotificationViewModel(repo)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    private fun notif(id: String, read: Boolean = false) =
        Notification(id = id, title = "t$id", body = "b$id", isRead = read)

    @Test
    fun `进入加载列表和未读数`() = runTest(dispatcher) {
        coEvery { repo.list() } returns listOf(notif("n1"))
        coEvery { repo.unreadCount() } returns 3
        vm.enter()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.notifications.size)
        assertEquals(3, vm.uiState.value.unreadCount)
    }

    @Test
    fun `WS 新通知去重插顶`() = runTest(dispatcher) {
        coEvery { repo.list() } returns emptyList()
        coEvery { repo.unreadCount() } returns 0
        vm.enter()
        dispatcher.scheduler.advanceUntilIdle()
        events.emit(NotificationSocketEvent.NewNotification(notif("n1")))
        events.emit(NotificationSocketEvent.NewNotification(notif("n1"))) // 重复
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.notifications.size)
    }

    @Test
    fun `unread_count_changed 更新角标`() = runTest(dispatcher) {
        coEvery { repo.list() } returns emptyList()
        coEvery { repo.unreadCount() } returns 0
        vm.enter()
        dispatcher.scheduler.advanceUntilIdle()
        events.emit(NotificationSocketEvent.UnreadCount(7))
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(7, vm.uiState.value.unreadCount)
    }

    @Test
    fun `标单条已读更新状态和角标`() = runTest(dispatcher) {
        coEvery { repo.list() } returns listOf(notif("n1"), notif("n2"))
        coEvery { repo.unreadCount() } returns 2
        vm.enter()
        dispatcher.scheduler.advanceUntilIdle()
        vm.markRead("n1")
        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.notifications.first { it.id == "n1" }.isRead)
        assertEquals(1, vm.uiState.value.unreadCount)
        coVerify { repo.markRead("n1") }
    }

    @Test
    fun `全部已读清零`() = runTest(dispatcher) {
        coEvery { repo.list() } returns listOf(notif("n1"), notif("n2"))
        coEvery { repo.unreadCount() } returns 2
        vm.enter()
        dispatcher.scheduler.advanceUntilIdle()
        vm.markAllRead()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(0, vm.uiState.value.unreadCount)
        assertTrue(vm.uiState.value.notifications.all { it.isRead })
        coVerify { repo.markAllRead() }
    }
}
