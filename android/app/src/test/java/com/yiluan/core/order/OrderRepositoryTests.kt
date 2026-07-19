package com.yiluan.core.order

import com.yiluan.core.model.CreateOrderRequest
import com.yiluan.core.model.Order
import com.yiluan.core.model.PrepayResponse
import com.yiluan.core.network.OrderApi
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * OrderRepository 单测（ANDROID-DEV-B2-PATIENT）。
 * 重点验支付/业务状态解耦: mock 成功→复查 payment_state=paid; mockSuccess=false 不复查。
 */
class OrderRepositoryTests {

    private lateinit var orderApi: OrderApi
    private lateinit var repo: OrderRepository

    @Before
    fun setup() {
        orderApi = mockk(relaxed = true)
        repo = OrderRepository(orderApi)
    }

    private fun order(status: String = "created", paymentState: String? = null) = Order(
        id = "o1",
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

    @Test
    fun `payOrder mock 成功后复查订单确认 payment_state=paid`() = runTest {
        coEvery { orderApi.pay("o1") } returns
            PrepayResponse(paymentId = "pay1", provider = "mock", mockSuccess = true)
        coEvery { orderApi.getOrder("o1") } returns order(paymentState = "paid")
        val result = repo.payOrder("o1")
        assertTrue(result.success)
        assertEquals("paid", result.order?.paymentState)
        assertEquals("created", result.order?.status) // 解耦: 业务态不变
        coVerify { orderApi.getOrder("o1") }
    }

    @Test
    fun `payOrder mockSuccess=false 直接失败不复查`() = runTest {
        coEvery { orderApi.pay("o1") } returns
            PrepayResponse(paymentId = "pay1", provider = "mock", mockSuccess = false)
        val result = repo.payOrder("o1")
        assertFalse(result.success)
        assertNull(result.order)
        coVerify(exactly = 0) { orderApi.getOrder(any()) }
    }

    @Test
    fun `payOrder 复查后 payment_state 非 paid 判失败`() = runTest {
        coEvery { orderApi.pay("o1") } returns
            PrepayResponse(paymentId = "pay1", provider = "mock", mockSuccess = true)
        coEvery { orderApi.getOrder("o1") } returns order(paymentState = "failed")
        val result = repo.payOrder("o1")
        assertFalse(result.success)
    }

    @Test
    fun `createOrder 透传请求`() = runTest {
        val req = CreateOrderRequest(
            serviceType = "full_accompany",
            hospitalId = "h1",
            appointmentDate = "2026-08-01",
            appointmentTime = "09:00",
        )
        coEvery { orderApi.createOrder(req) } returns order()
        val o = repo.createOrder(req)
        assertEquals("o1", o.id)
    }

    @Test
    fun `listOrders 返回 items`() = runTest {
        coEvery { orderApi.listOrders(status = "created", page = 1, pageSize = 20) } returns
            com.yiluan.core.model.OrderListResponse(items = listOf(order()), total = 1)
        val list = repo.listOrders(status = "created")
        assertEquals(1, list.size)
    }
}
