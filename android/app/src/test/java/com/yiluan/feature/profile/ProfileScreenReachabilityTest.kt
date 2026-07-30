package com.yiluan.feature.profile

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import com.yiluan.feature.companion.CompanionViewModel
import io.mockk.every
import io.mockk.mockk
import kotlinx.coroutines.flow.MutableStateFlow
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * ProfileScreen 个人中心聚合页可达性 Compose 导航测试。
 * ANDROID-BUG-HUB-REACHABILITY-COMPOSE-TEST (AC6) — 补 #417 hub 零导航测试的 vacuous 缺口。
 * 静态可达(grep navigate 0→≥1)已由 hub test AC2-4 验；本测试补 AC6 运行时验证:
 * ProfileScreen 渲染各入口 + performClick 触发对应导航回调(证明用户点击真能到达)。
 * 文案用 values-en/strings.xml 英文(Robolectric 默认 en locale, 同 NavHostSmokeTest)。
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34])
class ProfileScreenReachabilityTest {

    @get:Rule
    val composeRule = createComposeRule()

    /** 造一个 uiState 非陪诊师(不显示陪诊员主页入口)的 mock VM。 */
    private fun mockViewModel(): ProfileViewModel {
        val vm = mockk<ProfileViewModel>(relaxed = true)
        every { vm.uiState } returns MutableStateFlow(ProfileUiState())
        return vm
    }

    @Test
    fun `聚合页渲染钱包家人紧急绑手机入口`() {
        composeRule.setContent {
            ProfileScreen(
                onEditProfile = {}, onBindPhone = {}, onWallet = {}, onFamily = {},
                onEmergency = {}, onFollowups = {}, onNotifications = {}, onSettings = {},
                onAbout = {}, onCompanionHome = {}, viewModel = mockViewModel(),
            )
        }
        composeRule.onNodeWithText("My wallet").assertExists()
        composeRule.onNodeWithText("Family members").assertExists()
        composeRule.onNodeWithText("Emergency contacts").assertExists()
        composeRule.onNodeWithText("Bind phone").assertExists()
    }

    @Test
    fun `点击钱包触发导航回调`() {
        var walletClicked = false
        composeRule.setContent {
            ProfileScreen(
                onEditProfile = {}, onBindPhone = {}, onWallet = { walletClicked = true },
                onFamily = {}, onEmergency = {}, onFollowups = {}, onNotifications = {},
                onSettings = {}, onAbout = {}, onCompanionHome = {}, viewModel = mockViewModel(),
            )
        }
        composeRule.onNodeWithText("My wallet").performClick()
        assertTrue(walletClicked)
    }

    @Test
    fun `点击家人管理触发导航回调`() {
        var familyClicked = false
        composeRule.setContent {
            ProfileScreen(
                onEditProfile = {}, onBindPhone = {}, onWallet = {},
                onFamily = { familyClicked = true }, onEmergency = {}, onFollowups = {},
                onNotifications = {}, onSettings = {}, onAbout = {}, onCompanionHome = {},
                viewModel = mockViewModel(),
            )
        }
        composeRule.onNodeWithText("Family members").performClick()
        assertTrue(familyClicked)
    }

    @Test
    fun `点击紧急联系人触发导航回调`() {
        var emergencyClicked = false
        composeRule.setContent {
            ProfileScreen(
                onEditProfile = {}, onBindPhone = {}, onWallet = {}, onFamily = {},
                onEmergency = { emergencyClicked = true }, onFollowups = {},
                onNotifications = {}, onSettings = {}, onAbout = {}, onCompanionHome = {},
                viewModel = mockViewModel(),
            )
        }
        composeRule.onNodeWithText("Emergency contacts").performClick()
        assertTrue(emergencyClicked)
    }

    @Test
    fun `点击绑手机触发导航回调`() {
        var bindClicked = false
        composeRule.setContent {
            ProfileScreen(
                onEditProfile = {}, onBindPhone = { bindClicked = true }, onWallet = {},
                onFamily = {}, onEmergency = {}, onFollowups = {}, onNotifications = {},
                onSettings = {}, onAbout = {}, onCompanionHome = {}, viewModel = mockViewModel(),
            )
        }
        composeRule.onNodeWithText("Bind phone").performClick()
        assertTrue(bindClicked)
    }
}
