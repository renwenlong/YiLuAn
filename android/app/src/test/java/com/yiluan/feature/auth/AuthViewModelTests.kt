package com.yiluan.feature.auth

import com.yiluan.core.auth.AuthRepository
import com.yiluan.core.model.User
import com.yiluan.core.model.UserRole
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
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test

/**
 * AuthViewModel 状态机单测（ANDROID-DEV-B1-AUTH）。
 * 覆盖: 发OTP阶段切换 / 验证成功路由决策(role==null→ROLE_SELECT, 有role→DONE) /
 *      选角色成功→DONE / 手机号&验证码校验 / 错误处理。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class AuthViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var repository: AuthRepository
    private lateinit var vm: AuthViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        repository = mockk(relaxed = true)
        vm = AuthViewModel(repository)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    private fun userWith(role: String?): User =
        User(id = "u1", phone = "13800138000", role = role)

    @Test
    fun `手机号非数字被过滤且限长11`() {
        vm.onPhoneChange("138-abc-0013800138")
        assertEquals("13800138001", vm.uiState.value.phone)
    }

    @Test
    fun `合法手机号 isPhoneValid 为真`() {
        vm.onPhoneChange("13800138000")
        assert(vm.isPhoneValid)
        vm.onPhoneChange("12345")
        assert(!vm.isPhoneValid)
    }

    @Test
    fun `发送OTP成功后进入OTP输入阶段`() = runTest(dispatcher) {
        coEvery { repository.sendOtp("13800138000") } returns Unit
        vm.onPhoneChange("13800138000")
        vm.sendOtp()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(AuthStage.OTP_INPUT, vm.uiState.value.stage)
        coVerify { repository.sendOtp("13800138000") }
    }

    @Test
    fun `非法手机号发送OTP报错不调后端`() = runTest(dispatcher) {
        vm.onPhoneChange("123")
        vm.sendOtp()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ErrorKey.INVALID_PHONE, vm.uiState.value.errorMessage)
        assertEquals(AuthStage.PHONE_INPUT, vm.uiState.value.stage)
        coVerify(exactly = 0) { repository.sendOtp(any()) }
    }

    @Test
    fun `发送OTP失败设置错误key`() = runTest(dispatcher) {
        coEvery { repository.sendOtp(any()) } throws RuntimeException("net")
        vm.onPhoneChange("13800138000")
        vm.sendOtp()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ErrorKey.SEND_OTP_FAILED, vm.uiState.value.errorMessage)
    }

    @Test
    fun `验证OTP成功且role为null进入选角色阶段`() = runTest(dispatcher) {
        coEvery { repository.verifyOtp("13800138000", "123456") } returns userWith(null)
        vm.onPhoneChange("13800138000")
        vm.onCodeChange("123456")
        vm.verifyOtp()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(AuthStage.ROLE_SELECT, vm.uiState.value.stage)
    }

    @Test
    fun `验证OTP成功且role有值直接DONE`() = runTest(dispatcher) {
        coEvery { repository.verifyOtp("13800138000", "123456") } returns userWith("patient")
        vm.onPhoneChange("13800138000")
        vm.onCodeChange("123456")
        vm.verifyOtp()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(AuthStage.DONE, vm.uiState.value.stage)
    }

    @Test
    fun `验证OTP失败设置错误key保持OTP阶段`() = runTest(dispatcher) {
        coEvery { repository.verifyOtp(any(), any()) } throws RuntimeException("bad code")
        vm.onPhoneChange("13800138000")
        vm.onCodeChange("123456")
        vm.verifyOtp()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ErrorKey.VERIFY_OTP_FAILED, vm.uiState.value.errorMessage)
    }

    @Test
    fun `非法验证码不调后端`() = runTest(dispatcher) {
        vm.onPhoneChange("13800138000")
        vm.onCodeChange("12")
        vm.verifyOtp()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ErrorKey.INVALID_CODE, vm.uiState.value.errorMessage)
        coVerify(exactly = 0) { repository.verifyOtp(any(), any()) }
    }

    @Test
    fun `选角色成功进入DONE并带user`() = runTest(dispatcher) {
        coEvery { repository.setRole("patient") } returns userWith("patient")
        vm.selectRole(UserRole.PATIENT)
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(AuthStage.DONE, vm.uiState.value.stage)
        assertEquals("patient", vm.uiState.value.user?.role)
        coVerify { repository.setRole("patient") }
    }

    @Test
    fun `选角色失败设置错误key`() = runTest(dispatcher) {
        coEvery { repository.setRole(any()) } throws RuntimeException("net")
        vm.selectRole(UserRole.COMPANION)
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ErrorKey.SET_ROLE_FAILED, vm.uiState.value.errorMessage)
    }

    @Test
    fun `OTP页返回回到手机号阶段并清码`() {
        vm.onCodeChange("123456")
        vm.backToPhoneInput()
        assertEquals(AuthStage.PHONE_INPUT, vm.uiState.value.stage)
        assertEquals("", vm.uiState.value.code)
        assertNull(vm.uiState.value.errorMessage)
    }
}
