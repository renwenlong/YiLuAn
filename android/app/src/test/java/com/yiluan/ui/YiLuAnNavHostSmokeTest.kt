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
 *  - YiLuAnNavHost 能 setContent 渲染不崩，起始屏显示「医路安」
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
    }

    @Test
    fun `NavHost 渲染起始屏不崩`() {
        composeRule.setContent {
            YiLuAnNavHost()
        }
        // 起始 splash 屏显示 app 名，证明单 Activity + Navigation 骨架跑通。
        composeRule.onNodeWithText("医路安").assertExists()
    }
}
