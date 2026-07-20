package com.yiluan.feature.order

import com.yiluan.core.model.Hospital
import com.yiluan.core.model.Order
import com.yiluan.core.model.ServiceType
import com.yiluan.core.order.HospitalRepository
import com.yiluan.core.order.OrderRepository
import com.yiluan.core.order.PayResult
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * OrderViewModel 状态机单测（ANDROID-DEV-B2-PATIENT）。
 * 覆盖: 列表加载/过滤 / 详情 / 支付(成功&失败, 解耦语义) / 下单(校验&成功&失败) / 取消。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class OrderViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var orderRepo: OrderRepository
    private lateinit var hospitalRepo: HospitalRepository
    private lateinit var vm: OrderViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        orderRepo = mockk(relaxed = true)
        hospitalRepo = mockk(relaxed = true)
        vm = OrderViewModel(orderRepo, hospitalRepo)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    private fun order(
        id: String = "o1",
        status: String = "created",
        paymentState: String? = null,
    ) = Order(
        id = id,
        orderNumber = "YL001",
        patientId = "p1",
        hospitalId = "h1",
        serviceType = "full_accompany",
        status = status,
        appointmentDate = "2026-08-01",
        appointmentTime = "09:00",
        price = "199.00",
        paymentState = paymentState,
    )

    private fun hospital() = Hospital(id = "h1", name = "北京协和医院")

    @Test
    fun `加载订单列表成功`() = runTest(dispatcher) {
        coEvery { orderRepo.listOrders(status = null) } returns listOf(order())
        vm.loadOrders()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.orders.size)
        assertFalse(vm.uiState.value.isLoadingList)
    }

    @Test
    fun `加载订单列表按状态过滤`() = runTest(dispatcher) {
        coEvery { orderRepo.listOrders(status = "created") } returns emptyList()
        vm.loadOrders(status = "created")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals("created", vm.uiState.value.listFilter)
        coVerify { orderRepo.listOrders(status = "created") }
    }

    @Test
    fun `列表加载失败设 listError`() = runTest(dispatcher) {
        coEvery { orderRepo.listOrders(status = null) } throws RuntimeException("net")
        vm.loadOrders()
        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.listError)
    }

    @Test
    fun `加载订单详情成功`() = runTest(dispatcher) {
        coEvery { orderRepo.getOrder("o1") } returns order()
        vm.loadOrderDetail("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals("o1", vm.uiState.value.selectedOrder?.id)
    }

    @Test
    fun `支付成功弹 SUCCESS 并更新订单为已支付`() = runTest(dispatcher) {
        val paid = order(paymentState = "paid")
        coEvery { orderRepo.payOrder("o1") } returns PayResult(success = true, order = paid)
        vm.payOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(PayOutcomeUi.SUCCESS, vm.uiState.value.payResult)
        assertEquals("paid", vm.uiState.value.selectedOrder?.paymentState)
        // 解耦: 业务 status 仍 created
        assertEquals("created", vm.uiState.value.selectedOrder?.status)
    }

    @Test
    fun `支付失败弹 FAILED`() = runTest(dispatcher) {
        coEvery { orderRepo.payOrder("o1") } returns PayResult(success = false)
        vm.payOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(PayOutcomeUi.FAILED, vm.uiState.value.payResult)
    }

    @Test
    fun `支付异常弹 FAILED`() = runTest(dispatcher) {
        coEvery { orderRepo.payOrder("o1") } throws RuntimeException("net")
        vm.payOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(PayOutcomeUi.FAILED, vm.uiState.value.payResult)
    }

    @Test
    fun `dismissPayResult 清空结果`() = runTest(dispatcher) {
        coEvery { orderRepo.payOrder("o1") } returns PayResult(success = false)
        vm.payOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        vm.dismissPayResult()
        assertNull(vm.uiState.value.payResult)
    }

    @Test
    fun `未选医院不能提交下单`() {
        assertFalse(vm.canSubmitOrder)
    }

    @Test
    fun `选医院填日期时间后可提交`() {
        vm.onSelectHospital(hospital())
        vm.onDateChange("2026-08-01")
        vm.onTimeChange("09:00")
        assertTrue(vm.canSubmitOrder)
    }

    @Test
    fun `提交下单成功回调新订单并清草稿`() = runTest(dispatcher) {
        coEvery { orderRepo.createOrder(any()) } returns order(id = "new1")
        vm.onSelectHospital(hospital())
        vm.onServiceTypeChange(ServiceType.HALF_ACCOMPANY)
        vm.onDateChange("2026-08-01")
        vm.onTimeChange("09:00")
        var created: Order? = null
        vm.submitOrder { created = it }
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals("new1", created?.id)
        assertNull(vm.uiState.value.draft.hospital) // 草稿已清
    }

    @Test
    fun `提交下单失败设 CREATE_FAILED`() = runTest(dispatcher) {
        coEvery { orderRepo.createOrder(any()) } throws RuntimeException("net")
        vm.onSelectHospital(hospital())
        vm.onDateChange("2026-08-01")
        vm.onTimeChange("09:00")
        vm.submitOrder { }
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(OrderErrorKey.CREATE_FAILED, vm.uiState.value.actionError)
    }

    @Test
    fun `取消订单成功更新详情`() = runTest(dispatcher) {
        coEvery { orderRepo.cancelOrder("o1") } returns order(status = "cancelled_by_patient")
        vm.cancelOrder("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals("cancelled_by_patient", vm.uiState.value.selectedOrder?.status)
    }

    @Test
    fun `搜索医院更新候选`() = runTest(dispatcher) {
        coEvery { hospitalRepo.searchHospitals("协和") } returns listOf(hospital())
        vm.searchHospitals("协和")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.hospitals.size)
    }
}
