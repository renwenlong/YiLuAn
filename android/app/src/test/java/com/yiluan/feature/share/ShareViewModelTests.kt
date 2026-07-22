package com.yiluan.feature.share

import com.yiluan.core.model.CreateShareResponse
import com.yiluan.core.model.ExchangeSessionResponse
import com.yiluan.core.model.OrderShareToken
import com.yiluan.core.model.ShareSendOtpResponse
import com.yiluan.core.share.ShareRepository
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
import org.junit.Before
import org.junit.Test

/**
 * ShareViewModel 单测（ANDROID-DEV-B5-PRECHECK-SHARE）。
 * 覆盖: 发起端 createShare/list/revoke + 接收端 OTP 状态机(sendOtp→enterOtp/exchange→success) + 校验。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ShareViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var repo: ShareRepository
    private lateinit var vm: ShareViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        repo = mockk(relaxed = true)
        vm = ShareViewModel(repo)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    private fun token(id: String = "t1") = OrderShareToken(
        id = id, shareToken = "tok", shareUrl = "https://m.yiluan.cn/s/tok", shareScope = "progress_only",
    )

    @Test
    fun `加载发起端分享列表`() = runTest(dispatcher) {
        coEvery { repo.listShares("o1") } returns listOf(token())
        vm.loadShares("o1")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.shares.size)
    }

    @Test
    fun `创建分享成功后重拉列表`() = runTest(dispatcher) {
        coEvery { repo.createShare("o1", "progress_only") } returns
            CreateShareResponse(id = "t1", shareToken = "tok", shareUrl = "u", shareScope = "progress_only")
        coEvery { repo.listShares("o1") } returns listOf(token())
        vm.createShare("o1", "progress_only")
        dispatcher.scheduler.advanceUntilIdle()
        coVerify { repo.createShare("o1", "progress_only") }
        assertEquals(1, vm.uiState.value.shares.size)
    }

    @Test
    fun `撤销分享后重拉`() = runTest(dispatcher) {
        coEvery { repo.listShares("o1") } returns emptyList()
        vm.revokeShare("o1", "t1")
        dispatcher.scheduler.advanceUntilIdle()
        coVerify { repo.revokeShare("o1", "t1") }
    }

    @Test
    fun `OTP 非法手机号报错不调后端`() = runTest(dispatcher) {
        vm.onPhoneChange("123")
        vm.sendOtp("tok")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ShareErrorKey.INVALID_PHONE, vm.uiState.value.error)
        coVerify(exactly = 0) { repo.sendOtp(any(), any()) }
    }

    @Test
    fun `发送 OTP 成功进入输码阶段`() = runTest(dispatcher) {
        coEvery { repo.sendOtp("tok", "13800138000") } returns
            ShareSendOtpResponse(sent = true, maskedPhone = "138****8000", expiresIn = 300)
        vm.onPhoneChange("13800138000")
        vm.sendOtp("tok")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(OtpStage.ENTER_OTP, vm.uiState.value.otpStage)
        assertEquals("138****8000", vm.uiState.value.maskedPhone)
    }

    @Test
    fun `验证 OTP 成功进入 SUCCESS`() = runTest(dispatcher) {
        coEvery { repo.exchangeSession("tok", "13800138000", "123456") } returns
            ExchangeSessionResponse(shareSession = "jwt", shareScope = "full", orderId = "o1")
        coEvery { repo.shareOrder() } returns null
        vm.onPhoneChange("13800138000")
        vm.onOtpChange("123456")
        vm.exchangeSession("tok")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(OtpStage.SUCCESS, vm.uiState.value.otpStage)
    }

    @Test
    fun `验证 OTP 非法验证码报错`() = runTest(dispatcher) {
        vm.onPhoneChange("13800138000")
        vm.onOtpChange("12")
        vm.exchangeSession("tok")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ShareErrorKey.INVALID_OTP, vm.uiState.value.error)
        coVerify(exactly = 0) { repo.exchangeSession(any(), any(), any()) }
    }

    @Test
    fun `OrderShareToken 计算属性`() {
        val t = token()
        assertFalse(t.isRevoked)
        assertEquals(com.yiluan.core.model.ShareScope.PROGRESS_ONLY, t.scope)
    }
}
