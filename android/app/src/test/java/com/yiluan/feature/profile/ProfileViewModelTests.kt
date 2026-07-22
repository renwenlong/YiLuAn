package com.yiluan.feature.profile

import com.yiluan.core.model.EmergencyContact
import com.yiluan.core.model.FamilyMemberProfile
import com.yiluan.core.model.FollowupReminder
import com.yiluan.core.model.WalletSummary
import com.yiluan.core.profile.ProfileRepository
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
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * ProfileViewModel 单测（ANDROID-DEV-B6-LONGTAIL）。
 * 覆盖: family 加载/添加校验 / emergency 添加校验 / wallet / bindPhone 校验 / deleteAccount。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ProfileViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var repo: ProfileRepository
    private lateinit var vm: ProfileViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        repo = mockk(relaxed = true)
        vm = ProfileViewModel(repo)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `加载家庭成员成功`() = runTest(dispatcher) {
        coEvery { repo.listFamilyMembers() } returns listOf(FamilyMemberProfile(id = "f1", name = "张三"))
        vm.loadFamilyMembers()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.familyMembers.size)
    }

    @Test
    fun `添加家庭成员空名报错不调后端`() = runTest(dispatcher) {
        vm.addFamilyMember(name = "", relation = "other", phone = null)
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ProfileErrorKey.INVALID_INPUT, vm.uiState.value.error)
        coVerify(exactly = 0) { repo.createFamilyMember(any()) }
    }

    @Test
    fun `添加家庭成员成功后重新加载`() = runTest(dispatcher) {
        coEvery { repo.createFamilyMember(any()) } returns FamilyMemberProfile(id = "f1", name = "张三")
        coEvery { repo.listFamilyMembers() } returns listOf(FamilyMemberProfile(id = "f1", name = "张三"))
        vm.addFamilyMember(name = "张三", relation = "parent", phone = "13800138000")
        dispatcher.scheduler.advanceUntilIdle()
        coVerify { repo.createFamilyMember(any()) }
        assertEquals(1, vm.uiState.value.familyMembers.size)
    }

    @Test
    fun `添加紧急联系人非法手机号报错`() = runTest(dispatcher) {
        vm.addEmergencyContact(name = "张三", phone = "123", relationship = "friend")
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ProfileErrorKey.INVALID_INPUT, vm.uiState.value.error)
        coVerify(exactly = 0) { repo.createEmergencyContact(any()) }
    }

    @Test
    fun `加载紧急联系人成功`() = runTest(dispatcher) {
        coEvery { repo.listEmergencyContacts() } returns
            listOf(EmergencyContact(id = "e1", name = "李四", phone = "13800138000"))
        vm.loadEmergencyContacts()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(1, vm.uiState.value.emergencyContacts.size)
    }

    @Test
    fun `加载钱包概览+流水`() = runTest(dispatcher) {
        coEvery { repo.walletSummary() } returns WalletSummary(balance = "100.00")
        coEvery { repo.walletTransactions() } returns emptyList()
        vm.loadWallet()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals("100.00", vm.uiState.value.wallet?.balance)
    }

    @Test
    fun `绑手机非法输入报错不调后端`() = runTest(dispatcher) {
        vm.bindPhone(phone = "123", code = "12", onSuccess = {})
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ProfileErrorKey.INVALID_INPUT, vm.uiState.value.error)
        coVerify(exactly = 0) { repo.bindPhone(any(), any()) }
    }

    @Test
    fun `绑手机成功回调`() = runTest(dispatcher) {
        coEvery { repo.bindPhone("13800138000", "123456") } returns
            com.yiluan.core.model.User(id = "u1")
        var ok = false
        vm.bindPhone(phone = "13800138000", code = "123456", onSuccess = { ok = true })
        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(ok)
    }

    @Test
    fun `注销成功回调并清 token`() = runTest(dispatcher) {
        coEvery { repo.deleteAccount() } returns Unit
        var deleted = false
        vm.deleteAccount(onDeleted = { deleted = true })
        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(deleted)
        coVerify { repo.deleteAccount() }
    }

    @Test
    fun `注销失败设错误 key`() = runTest(dispatcher) {
        coEvery { repo.deleteAccount() } throws RuntimeException("net")
        vm.deleteAccount(onDeleted = {})
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ProfileErrorKey.DELETE_FAILED, vm.uiState.value.error)
    }

    // ---- 复诊提醒补漏页 (ANDROID-DEV-GAP-FOLLOWUP-REMINDERS) ----

    private fun reminder(id: String, status: String = "pending") =
        FollowupReminder(id = id, orderId = "o1", remindAt = "2026-08-01 09:00", status = status)

    @Test
    fun `加载复诊提醒成功`() = runTest(dispatcher) {
        coEvery { repo.listFollowups() } returns listOf(reminder("r1"), reminder("r2"))
        vm.loadFollowups()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(2, vm.uiState.value.followups.size)
        assertEquals(false, vm.uiState.value.isLoadingFollowups)
    }

    @Test
    fun `加载复诊提醒空态`() = runTest(dispatcher) {
        coEvery { repo.listFollowups() } returns emptyList()
        vm.loadFollowups()
        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(vm.uiState.value.followups.isEmpty())
    }

    @Test
    fun `加载复诊提醒失败设错误 key`() = runTest(dispatcher) {
        coEvery { repo.listFollowups() } throws RuntimeException("net")
        vm.loadFollowups()
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ProfileErrorKey.LOAD_FAILED, vm.uiState.value.error)
        assertEquals(false, vm.uiState.value.isLoadingFollowups)
    }

    @Test
    fun `删除复诊提醒成功后重拉`() = runTest(dispatcher) {
        coEvery { repo.deleteFollowup("r1") } returns Unit
        coEvery { repo.listFollowups() } returns emptyList()
        vm.deleteFollowup("r1")
        dispatcher.scheduler.advanceUntilIdle()
        coVerify { repo.deleteFollowup("r1") }
        coVerify { repo.listFollowups() }
    }
}
