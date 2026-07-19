package com.yiluan.ui

import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import org.junit.Assert.assertEquals
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * NavHost 导航骨架 smoke（ANDROID-BUG-B0-TEST-COVERAGE-GAP AC5: 导航骨架跑通）。
 * 用 Robolectric + Compose test 在 JVM 验：
 *  - Routes 契约（START_DESTINATION = SPLASH）
 *  - YiLuAnNavHost 能 setContent 渲染不崩
 *
 * ANDROID-DEV-B1-AUTH: splash 起始屏现依赖 Hilt ViewModel（查 token 路由决策），
 * 纯 JVM smoke 无 Hilt 容器，故用 startDestination=HOME 直接验占位屏渲染贯通，
 * 避开 splash 的 DI 依赖（登录流程完整测试见 AuthViewModelTests）。
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34])
class YiLuAnNavHostSmokeTest {

    @get:Rule
    val composeRule = createComposeRule()

    @Test
    fun `Routes 起始目的地契约`() {
        assertEquals("splash", Routes.SPLASH)
        assertEquals(Routes.SPLASH, Routes.START_DESTINATION)
        assertEquals("auth", Routes.AUTH)
        assertEquals("home", Routes.HOME)
        assertEquals("create_order", Routes.CREATE_ORDER)
        assertEquals("order_list", Routes.ORDER_LIST)
        assertEquals("order_detail/o1", Routes.orderDetail("o1"))
    }

    @Test
    fun `NavHost 渲染患者首页不崩`() {
        composeRule.setContent {
            YiLuAnNavHost(startDestination = Routes.HOME)
        }
        // HOME = 患者首页（无 Hilt 依赖），验下单入口按钮文案存在，
        // 证明单 Activity + Navigation 骨架 + B2 患者入口贯通。
        composeRule.onNodeWithText("立即下单").assertExists()
    }
}
