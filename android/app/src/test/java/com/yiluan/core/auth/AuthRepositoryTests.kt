package com.yiluan.core.auth

import com.yiluan.core.model.SendOtpRequest
import com.yiluan.core.model.SendOtpResponse
import com.yiluan.core.model.SwitchRoleRequest
import com.yiluan.core.model.TokenResponse
import com.yiluan.core.model.UpdateMeRequest
import com.yiluan.core.model.User
import com.yiluan.core.model.VerifyOtpRequest
import com.yiluan.core.network.AuthApi
import com.yiluan.core.network.UserApi
import com.yiluan.core.storage.TokenStore
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.test.runTest
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/**
 * AuthRepository 单测（ANDROID-DEV-B1-AUTH）。
 * 重点验: verifyOtp 存 token / switchRole 换新 token 必重存 / setRole 不换 token /
 *        hasToken 判断登录态。
 */
class AuthRepositoryTests {

    private lateinit var authApi: AuthApi
    private lateinit var userApi: UserApi
    private lateinit var tokenStore: TokenStore
    private lateinit var repo: AuthRepository

    @Before
    fun setup() {
        authApi = mockk(relaxed = true)
        userApi = mockk(relaxed = true)
        tokenStore = mockk(relaxed = true)
        repo = AuthRepository(authApi, userApi, tokenStore)
    }

    private fun user(role: String?) = User(id = "u1", phone = "13800138000", role = role)

    @Test
    fun `sendOtp 透传手机号给后端`() = runTest {
        coEvery { authApi.sendOtp(any()) } returns SendOtpResponse("ok")
        repo.sendOtp("13800138000")
        coVerify { authApi.sendOtp(SendOtpRequest("13800138000")) }
    }

    @Test
    fun `verifyOtp 成功后存 token 并返回 user`() = runTest {
        coEvery { authApi.verifyOtp(VerifyOtpRequest("13800138000", "123456")) } returns
            TokenResponse(accessToken = "acc1", refreshToken = "ref1", user = user(null))
        val u = repo.verifyOtp("13800138000", "123456")
        assertEquals("u1", u.id)
        coVerify { tokenStore.saveTokens("acc1", "ref1") }
    }

    @Test
    fun `setRole 走 updateMe 且不动 token`() = runTest {
        coEvery { userApi.updateMe(UpdateMeRequest(role = "patient")) } returns user("patient")
        val u = repo.setRole("patient")
        assertEquals("patient", u.role)
        coVerify(exactly = 0) { tokenStore.saveTokens(any(), any()) }
    }

    @Test
    fun `switchRole 返回新 token 必须重存`() = runTest {
        coEvery { userApi.switchRole(SwitchRoleRequest("companion")) } returns
            TokenResponse(accessToken = "acc2", refreshToken = "ref2", user = user("companion"))
        val u = repo.switchRole("companion")
        assertEquals("companion", u.role)
        coVerify { tokenStore.saveTokens("acc2", "ref2") }
    }

    @Test
    fun `hasToken 有 access token 返回真`() = runTest {
        coEvery { tokenStore.accessToken() } returns "acc"
        assertTrue(repo.hasToken())
    }

    @Test
    fun `hasToken 无 token 返回假`() = runTest {
        coEvery { tokenStore.accessToken() } returns null
        assertFalse(repo.hasToken())
    }

    @Test
    fun `logout 清 token`() = runTest {
        repo.logout()
        coVerify { tokenStore.clear() }
    }
}
