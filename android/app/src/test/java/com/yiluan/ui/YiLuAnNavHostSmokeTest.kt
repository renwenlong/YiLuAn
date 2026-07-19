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
    }

    @Test
    fun `NavHost 渲染占位主界面不崩`() {
        composeRule.setContent {
            YiLuAnNavHost(startDestination = Routes.HOME)
        }
        // HOME 占位屏显示 app 名，证明单 Activity + Navigation 骨架跑通。
        composeRule.onNodeWithText("医路安").assertExists()
    }
}
