package com.yiluan.core.model

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Order/枚举 计算属性单测（ANDROID-DEV-B2-PATIENT）。
 * 验 canPay/canCancel 业务规则 + 枚举映射 + Hospital.tagList。
 */
class OrderModelTests {

    private fun order(status: String, paymentState: String? = null) = Order(
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
    fun `created 未支付可支付`() {
        assertTrue(order("created").canPay)
    }

    @Test
    fun `created 已支付不可再支付`() {
        assertFalse(order("created", paymentState = "paid").canPay)
    }

    @Test
    fun `accepted 不可支付`() {
        assertFalse(order("accepted").canPay)
    }

    @Test
    fun `created accepted in_progress 可取消`() {
        assertTrue(order("created").canCancel)
        assertTrue(order("accepted").canCancel)
        assertTrue(order("in_progress").canCancel)
    }

    @Test
    fun `completed 已完成不可取消`() {
        assertFalse(order("completed").canCancel)
    }

    @Test
    fun `OrderStatus 枚举映射真实值`() {
        assertEquals(OrderStatus.CREATED, OrderStatus.fromValue("created"))
        assertEquals(OrderStatus.IN_PROGRESS, OrderStatus.fromValue("in_progress"))
        assertEquals(OrderStatus.REJECTED_BY_COMPANION, OrderStatus.fromValue("rejected_by_companion"))
        // 过时值不映射
        assertNull(OrderStatus.fromValue("pending_payment"))
        assertNull(OrderStatus.fromValue("paid"))
    }

    @Test
    fun `PaymentState 与业务 status 独立`() {
        assertEquals(PaymentState.PAID, PaymentState.fromValue("paid"))
        assertEquals(PaymentState.PAYING, PaymentState.fromValue("paying"))
    }

    @Test
    fun `ServiceType 枚举映射`() {
        assertEquals(ServiceType.FULL_ACCOMPANY, ServiceType.fromValue("full_accompany"))
        assertEquals(ServiceType.ERRAND, ServiceType.fromValue("errand"))
    }

    @Test
    fun `Hospital tagList 逗号拆分`() {
        val h = Hospital(id = "h1", name = "协和", tags = "三甲, 综合 ,教学")
        assertEquals(listOf("三甲", "综合", "教学"), h.tagList)
    }

    @Test
    fun `Hospital 空 tags 返回空 list`() {
        assertTrue(Hospital(id = "h1", name = "协和").tagList.isEmpty())
    }
}
