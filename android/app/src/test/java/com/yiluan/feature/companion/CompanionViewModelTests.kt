package com.yiluan.feature.companion

import com.yiluan.core.companion.CompanionRepository
import com.yiluan.core.model.CompanionProfile
import com.yiluan.core.model.Order
import com.yiluan.core.model.ServiceType
import com.yiluan.core.order.OrderRepository
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

/**
 * CompanionViewModel 单测（ANDROID-DEV-B3-COMPANION）。
 * 覆盖: 抢单加载 / 接单成功 / PHONE_REQUIRED / VERIFICATION_REQUIRED /
 *      今日过滤 / 订单动作 / 入驻校验+成功/失败。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class CompanionViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var orderRepo: OrderRepository
    private lateinit var companionRepo: CompanionRepository
    private lateinit var vm: CompanionViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        orderRepo = mockk(relaxed = true)
        companionRepo = mockk(relaxed = true)
        vm = CompanionViewModel(orderRepo, companionRepo)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    private fun order(id: String = "o1", status: String = "created", date: String = "2026-08-01") = Order(
        id = id,
        orderNumber = "YL001",
        patientId = "p1",
        hospitalId = "h1",
        serviceType = "full_accompany",
        status = status,
        appointmentDate = date,
        appointmentTime = "09:00",
        price = "199.00",
    )

    /** 造一个带 error_code 的 HttpException。 */
    private fun httpError(code: String): HttpException {
        val body = """{"detail":{"code":"$code","message":"x"}}"""
            .toResponseBody("application/json".toMediaType())
        return HttpException(Response.error<Any>(400, body))
    }

    @Test
    fun `加载抢单大厅成功`() = runTest(dispatcher) {
        coEvery { orderRepo.listOrders(status = "created") } returns listOf(order())
        vm.loadAvailableOrders()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.availableOrders.size)
    }

    @Test
    fun `接单成功刷新大厅`() = runTest(dispatcher) {
        coEvery { orderRepo.acceptOrder("o1") } returns order(status = "accepted")
        coEvery { orderRepo.listOrders(status = "created") } returns emptyList()
        vm.acceptOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(null, vm.uiState.value.actingOrderId)
        coVerify { orderRepo.acceptOrder("o1") }
    }

    @Test
    fun `接单 PHONE_REQUIRED 映射错误 key`() = runTest(dispatcher) {
        coEvery { orderRepo.acceptOrder("o1") } throws httpError("PHONE_REQUIRED")
        vm.acceptOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(CompanionErrorKey.PHONE_REQUIRED, vm.uiState.value.actionError)
    }

    @Test
    fun `接单 VERIFICATION_REQUIRED 映射错误 key`() = runTest(dispatcher) {
        coEvery { orderRepo.acceptOrder("o1") } throws httpError("VERIFICATION_REQUIRED")
        vm.acceptOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(CompanionErrorKey.VERIFICATION_REQUIRED, vm.uiState.value.actionError)
    }

    @Test
    fun `接单其他错误映射 ACCEPT_FAILED`() = runTest(dispatcher) {
        coEvery { orderRepo.acceptOrder("o1") } throws RuntimeException("net")
        vm.acceptOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(CompanionErrorKey.ACCEPT_FAILED, vm.uiState.value.actionError)
    }

    @Test
    fun `今日订单按日期前缀过滤`() = runTest(dispatcher) {
        coEvery { orderRepo.listOrders(status = "accepted") } returns listOf(
            order(id = "a", date = "2026-08-01"),
            order(id = "b", date = "2026-08-02"),
        )
        vm.loadTodayOrders("2026-08-01")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.todayOrders.size)
        assertEquals("a", vm.uiState.value.todayOrders.first().id)
    }

    @Test
    fun `完成服务更新详情`() = runTest(dispatcher) {
        coEvery { orderRepo.completeOrder("o1") } returns order(status = "completed")
        vm.completeService("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals("completed", vm.uiState.value.selectedOrder?.status)
    }

    @Test
    fun `未填真名不能提交入驻`() {
        vm.onApplyFieldChange { it.copy(serviceTypes = setOf(ServiceType.FULL_ACCOMPANY)) }
        assertFalse(vm.canSubmitApply)
    }

    @Test
    fun `填全真名和服务类型可提交入驻`() {
        vm.onApplyFieldChange { it.copy(realName = "张三", serviceTypes = setOf(ServiceType.ERRAND)) }
        assertTrue(vm.canSubmitApply)
    }

    @Test
    fun `提交入驻成功回调`() = runTest(dispatcher) {
        coEvery { companionRepo.apply(any()) } returns CompanionProfile(id = "c1")
        vm.onApplyFieldChange { it.copy(realName = "张三", serviceTypes = setOf(ServiceType.FULL_ACCOMPANY)) }
        var applied = false
        vm.submitApply { applied = true }
        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(applied)
        assertEquals("c1", vm.uiState.value.myProfile?.id)
    }

    @Test
    fun `提交入驻失败设错误 key`() = runTest(dispatcher) {
        coEvery { companionRepo.apply(any()) } throws RuntimeException("net")
        vm.onApplyFieldChange { it.copy(realName = "张三", serviceTypes = setOf(ServiceType.FULL_ACCOMPANY)) }
        vm.submitApply { }
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(CompanionErrorKey.APPLY_FAILED, vm.uiState.value.actionError)
    }

    @Test
    fun `加载公开陪诊员详情`() = runTest(dispatcher) {
        coEvery { companionRepo.companionDetail("c1") } returns
            CompanionProfile(id = "c1", pseudonymName = "张**", verificationStatus = "verified")
        vm.loadCompanionDetail("c1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals("张**", vm.uiState.value.viewedCompanion?.displayName)
        assertTrue(vm.uiState.value.viewedCompanion!!.isVerified)
    }
}
