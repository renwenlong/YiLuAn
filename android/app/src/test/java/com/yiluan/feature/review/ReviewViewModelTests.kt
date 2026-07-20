package com.yiluan.feature.review

import com.yiluan.core.model.ReviewResponse
import com.yiluan.core.review.ReviewRepository
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
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * ReviewViewModel 单测（ANDROID-DEV-B6-LONGTAIL）。
 * 覆盖: 维度评分 coerce / content 校验 / 提交成功(驱动订单 reviewed)/失败。
 */
@OptIn(ExperimentalCoroutinesApi::class)
class ReviewViewModelTests {

    private val dispatcher = StandardTestDispatcher()
    private lateinit var repo: ReviewRepository
    private lateinit var vm: ReviewViewModel

    @Before
    fun setup() {
        Dispatchers.setMain(dispatcher)
        repo = mockk(relaxed = true)
        vm = ReviewViewModel(repo)
    }

    @After
    fun teardown() {
        Dispatchers.resetMain()
    }

    @Test
    fun `维度评分限制在1到5`() {
        vm.setPunctuality(9)
        assertEquals(5, vm.uiState.value.punctuality)
        vm.setPunctuality(0)
        assertEquals(1, vm.uiState.value.punctuality)
    }

    @Test
    fun `content 不足5字不能提交`() {
        vm.setContent("好")
        assertFalse(vm.canSubmit)
    }

    @Test
    fun `content 满足5字可提交`() {
        vm.setContent("服务很好很棒")
        assertTrue(vm.canSubmit)
    }

    @Test
    fun `content 超500字被截断`() {
        vm.setContent("x".repeat(600))
        assertEquals(500, vm.uiState.value.content.length)
    }

    @Test
    fun `提交非法content报错不调后端`() = runTest(dispatcher) {
        vm.setContent("短")
        vm.submit("o1") {}
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ReviewErrorKey.CONTENT_INVALID, vm.uiState.value.error)
        coVerify(exactly = 0) { repo.submitReview(any(), any(), any(), any(), any(), any()) }
    }

    @Test
    fun `提交成功回调`() = runTest(dispatcher) {
        coEvery { repo.submitReview("o1", 5, 5, 5, 5, any()) } returns
            ReviewResponse(id = "r1", orderId = "o1")
        vm.setContent("服务非常好很专业")
        var submitted = false
        vm.submit("o1") { submitted = true }
        dispatcher.scheduler.advanceUntilIdle()
        assertTrue(submitted)
        assertTrue(vm.uiState.value.submitted)
    }

    @Test
    fun `提交失败设错误 key`() = runTest(dispatcher) {
        coEvery { repo.submitReview(any(), any(), any(), any(), any(), any()) } throws RuntimeException("net")
        vm.setContent("服务非常好很专业")
        vm.submit("o1") {}
        dispatcher.scheduler.advanceUntilIdle()
        assertEquals(ReviewErrorKey.SUBMIT_FAILED, vm.uiState.value.error)
    }
}
