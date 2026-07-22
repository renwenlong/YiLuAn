package com.yiluan.feature.precheck

import com.yiluan.core.model.OrderPrecheckSummary
import com.yiluan.core.precheck.PrecheckRepository
import com.yiluan.core.realtime.PrecheckSocket
import com.yiluan.core.realtime.PrecheckSocketEvent
import io.mockk.coEvery
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

/**
 * PrecheckViewModel 单测（ANDROID-DEV-B5-PRECHECK-SHARE）。
 * 覆盖: summary 加载 / 404 不阻断(notFound) / WS Invalidated 重拉 / Error close code。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class PrecheckViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var repo: PrecheckRepository
    private lateinit var socket: PrecheckSocket
    private lateinit var events: MutableSharedFlow<PrecheckSocketEvent>
    private lateinit var vm: PrecheckViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        repo = mockk(relaxed = true)
        socket = mockk(relaxed = true)
        events = MutableSharedFlow(extraBufferCapacity = 16)
        every { socket.events } returns events
        every { repo.createSocket(any(), any()) } returns socket
        vm = PrecheckViewModel(repo)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    private fun summary(allReady: Boolean = false) =
        OrderPrecheckSummary(orderId = "o1", allReady = allReady, paymentEnabled = allReady)

    private fun http404(): HttpException =
        HttpException(Response.error<Any>(404, "{}".toResponseBody("application/json".toMediaType())))

    @Test
    fun `进入拉 summary`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } returns summary(allReady = true)
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.summary?.allReady)
    }

    @Test
    fun `404 不阻断设 notFound`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } throws http404()
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.notFound)
        assertEquals(null, vm.uiState.value.summary)
    }

    @Test
    fun `WS Invalidated 触发重拉 summary`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } returns summary()
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        coEvery { repo.summary("o1") } returns summary(allReady = true)
        events.emit(PrecheckSocketEvent.Invalidated("precheck.all_ready"))
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(true, vm.uiState.value.summary?.allReady)
    }

    @Test
    fun `WS Error 设 wsError`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } returns summary()
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()
        events.emit(PrecheckSocketEvent.Error(4001))
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(4001, vm.uiState.value.wsError)
    }
}
