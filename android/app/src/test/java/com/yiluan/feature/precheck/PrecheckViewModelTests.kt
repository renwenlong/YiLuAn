package com.yiluan.feature.precheck

import com.yiluan.core.model.OrderPrecheckSummary
import com.yiluan.core.precheck.PrecheckRepository
import com.yiluan.core.realtime.PrecheckSocket
import com.yiluan.core.realtime.PrecheckSocketEvent
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

    // ---- AC1 轮询兜底覆盖 (ANDROID-BUG-B5-PRECHECK-POLL-COVERAGE) ----

    /** NeedPolling 触发轮询：间隔 3s 逐次重拉 summary（非空跑，时序驱动）。 */
    @Test
    fun `NeedPolling 触发轮询按 3s 间隔重拉 summary`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } returns summary(allReady = false)
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle() // enter 首拉 1 次

        events.emit(PrecheckSocketEvent.NeedPolling)
        dispatcher.scheduler.runCurrent() // 让 startPolling 协程起来

        // 未到 3s：不应新增轮询拉取
        dispatcher.scheduler.advanceTimeBy(2_000L)
        dispatcher.scheduler.runCurrent()
        coVerify(exactly = 1) { repo.summary("o1") }

        // 跨过第 1 个 3s 间隔：轮询第 1 次重拉
        dispatcher.scheduler.advanceTimeBy(1_500L)
        dispatcher.scheduler.runCurrent()
        coVerify(exactly = 2) { repo.summary("o1") }

        // 再跨 3s：轮询第 2 次重拉
        dispatcher.scheduler.advanceTimeBy(3_000L)
        dispatcher.scheduler.runCurrent()
        coVerify(exactly = 3) { repo.summary("o1") }
    }

    /** 轮询上限 MAX_POLL=10：始终 allReady=false 时最多轮询 10 次后停止（共 1 首拉 + 10 轮询 = 11）。 */
    @Test
    fun `轮询达上限 10 次后停止`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } returns summary(allReady = false)
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()

        events.emit(PrecheckSocketEvent.NeedPolling)
        // 推进足够长时间（远超 10*3s）：轮询应在第 10 次后自行停止
        dispatcher.scheduler.advanceTimeBy(60_000L)
        dispatcher.scheduler.advanceUntilIdle()

        // 1 次 enter 首拉 + 10 次轮询 = 11，不再增长
        coVerify(exactly = 11) { repo.summary("o1") }
    }

    /** allReady 达成时轮询提前 break，不再继续。 */
    @Test
    fun `轮询中 summary allReady 后提前停止`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } returns summary(allReady = false)
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()

        events.emit(PrecheckSocketEvent.NeedPolling)
        dispatcher.scheduler.runCurrent()

        // 第 1 次轮询前把 summary 切成 allReady=true
        coEvery { repo.summary("o1") } returns summary(allReady = true)
        dispatcher.scheduler.advanceTimeBy(3_000L) // 第 1 次轮询命中 allReady → break
        dispatcher.scheduler.runCurrent()
        assertEquals(true, vm.uiState.value.summary?.allReady)

        val callsAfterReady = 2 // enter 首拉 + 第 1 次轮询
        // 再推进大量时间：break 后不应继续轮询
        dispatcher.scheduler.advanceTimeBy(30_000L)
        dispatcher.scheduler.advanceUntilIdle()
        coVerify(exactly = callsAfterReady) { repo.summary("o1") }
    }

    /** WS 恢复(Connected)后停轮询：轮询中收到 Connected → pollJob 取消，不再重拉。 */
    @Test
    fun `WS Connected 停止轮询`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } returns summary(allReady = false)
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()

        events.emit(PrecheckSocketEvent.NeedPolling)
        dispatcher.scheduler.runCurrent()
        dispatcher.scheduler.advanceTimeBy(3_000L) // 第 1 次轮询
        dispatcher.scheduler.runCurrent()
        coVerify(exactly = 2) { repo.summary("o1") } // 首拉 + 1 轮询

        // WS 恢复 → 停轮询
        events.emit(PrecheckSocketEvent.Connected)
        dispatcher.scheduler.runCurrent()
        dispatcher.scheduler.advanceTimeBy(30_000L)
        dispatcher.scheduler.advanceUntilIdle()
        // 停轮询后调用次数不再增长
        coVerify(exactly = 2) { repo.summary("o1") }
    }

    /** 轮询幂等：pollJob 已 active 时重复 NeedPolling 不叠加第二个轮询协程。 */
    @Test
    fun `重复 NeedPolling 不叠加轮询`() = runTest(dispatcher) {
        coEvery { repo.summary("o1") } returns summary(allReady = false)
        vm.enter("o1")
        dispatcher.scheduler.advanceUntilIdle()

        events.emit(PrecheckSocketEvent.NeedPolling)
        dispatcher.scheduler.runCurrent()
        events.emit(PrecheckSocketEvent.NeedPolling) // 第二次应被幂等忽略
        dispatcher.scheduler.runCurrent()

        dispatcher.scheduler.advanceTimeBy(3_000L)
        dispatcher.scheduler.runCurrent()
        // 若叠加了第二个协程，此处会是 3（首拉+2轮询）；幂等则为 2（首拉+1轮询）
        coVerify(exactly = 2) { repo.summary("o1") }
    }
}
