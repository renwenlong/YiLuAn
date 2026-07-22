package com.yiluan.feature.order

import androidx.compose.ui.test.assertIsDisplayed
import androidx.compose.ui.test.assertDoesNotExist
import androidx.compose.ui.test.junit4.createComposeRule
import androidx.compose.ui.test.onNodeWithText
import androidx.compose.ui.test.performClick
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode

/**
 * PaymentResultScreen 独立支付结果页 Compose UI 测试。
 * ANDROID-BUG-GAP-PAYRESULT-TEST-COVERAGE — 补 #411 vacuous pass(独立页零测试)。
 * 验 AC1 成功态引导(viewOrder/goHome) / AC2 失败态引导(retry/viewOrder) / 按钮回调触发。
 * 文案用 values/strings.xml 中文默认(Robolectric 默认 locale)。
 */
@RunWith(RobolectricTestRunner::class)
@GraphicsMode(GraphicsMode.Mode.NATIVE)
@Config(sdk = [34])
class PaymentResultScreenTest {

    @get:Rule
    val composeRule = createComposeRule()

    // AC1: 成功态显示 viewOrder + goHome 引导按钮
    @Test
    fun `成功态显示查看订单和返回首页按钮`() {
        composeRule.setContent {
            PaymentResultScreen(isSuccess = true, onViewOrder = {}, onGoHome = {}, onRetry = {})
        }
        composeRule.onNodeWithText("查看订单").assertIsDisplayed()
        composeRule.onNodeWithText("返回首页").assertIsDisplayed()
    }

    // AC1: 成功态不显示失败态的重试按钮
    @Test
    fun `成功态不显示重试按钮`() {
        composeRule.setContent {
            PaymentResultScreen(isSuccess = true, onViewOrder = {}, onGoHome = {}, onRetry = {})
        }
        composeRule.onNodeWithText("重试支付").assertDoesNotExist()
    }

    // AC2: 失败态显示 retry + viewOrder 引导按钮
    @Test
    fun `失败态显示重试和查看订单按钮`() {
        composeRule.setContent {
            PaymentResultScreen(isSuccess = false, onViewOrder = {}, onGoHome = {}, onRetry = {})
        }
        composeRule.onNodeWithText("重试支付").assertIsDisplayed()
        composeRule.onNodeWithText("查看订单").assertIsDisplayed()
    }

    // AC2: 失败态不显示成功态的返回首页按钮
    @Test
    fun `失败态不显示返回首页按钮`() {
        composeRule.setContent {
            PaymentResultScreen(isSuccess = false, onViewOrder = {}, onGoHome = {}, onRetry = {})
        }
        composeRule.onNodeWithText("返回首页").assertDoesNotExist()
    }

    // AC3: 成功态点击 viewOrder 触发回调
    @Test
    fun `成功态点击查看订单触发回调`() {
        var viewOrderClicked = false
        composeRule.setContent {
            PaymentResultScreen(
                isSuccess = true,
                onViewOrder = { viewOrderClicked = true },
                onGoHome = {},
                onRetry = {},
            )
        }
        composeRule.onNodeWithText("查看订单").performClick()
        assertTrue(viewOrderClicked)
    }

    // AC3: 成功态点击 goHome 触发回调
    @Test
    fun `成功态点击返回首页触发回调`() {
        var goHomeClicked = false
        composeRule.setContent {
            PaymentResultScreen(
                isSuccess = true,
                onViewOrder = {},
                onGoHome = { goHomeClicked = true },
                onRetry = {},
            )
        }
        composeRule.onNodeWithText("返回首页").performClick()
        assertTrue(goHomeClicked)
    }

    // AC3: 失败态点击 retry 触发回调
    @Test
    fun `失败态点击重试触发回调`() {
        var retryClicked = false
        composeRule.setContent {
            PaymentResultScreen(
                isSuccess = false,
                onViewOrder = {},
                onGoHome = {},
                onRetry = { retryClicked = true },
            )
        }
        composeRule.onNodeWithText("重试支付").performClick()
        assertTrue(retryClicked)
    }
}
