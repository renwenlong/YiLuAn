package com.yiluan.core.network

import com.yiluan.core.model.TokenPair
import io.mockk.coEvery
import io.mockk.coVerify
import io.mockk.mockk
import kotlinx.coroutines.runBlocking
import com.yiluan.core.storage.TokenStore
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import javax.inject.Provider

/**
 * AuthInterceptor 单测（ANDROID-DEV-B0-CORE AC: 401 自动 refresh token）。
 * 用 MockWebServer 驱动真实 OkHttp 调用链，mockk 桩 TokenStore/AuthApi。
 */
class AuthInterceptorTest {

    private lateinit var server: MockWebServer
    private lateinit var tokenStore: TokenStore
    private lateinit var authApi: AuthApi
    private lateinit var client: OkHttpClient

    @Before
    fun setup() {
        server = MockWebServer()
        server.start()
        tokenStore = mockk(relaxed = true)
        authApi = mockk()
        val interceptor = AuthInterceptor(tokenStore, Provider { authApi })
        client = OkHttpClient.Builder().addInterceptor(interceptor).build()
    }

    @After
    fun teardown() {
        server.shutdown()
    }

    private fun call(): okhttp3.Response {
        val req = Request.Builder().url(server.url("/orders")).build()
        return client.newCall(req).execute()
    }

    @Test
    fun `注入 access token 到 Authorization`() {
        coEvery { tokenStore.accessToken() } returns "acc1"
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))

        call().close()

        val recorded = server.takeRequest()
        assertEquals("Bearer acc1", recorded.getHeader("Authorization"))
    }

    @Test
    fun `未登录时不注入 Authorization 原样放行`() {
        coEvery { tokenStore.accessToken() } returns null
        server.enqueue(MockResponse().setResponseCode(200).setBody("{}"))

        call().close()

        val recorded = server.takeRequest()
        assertNull(recorded.getHeader("Authorization"))
    }

    @Test
    fun `401 触发 refresh 并用新 token 重放请求`() {
        coEvery { tokenStore.accessToken() } returns "stale"
        coEvery { tokenStore.refreshToken() } returns "refresh1"
        coEvery { authApi.refresh(any()) } returns
            TokenPair(accessToken = "fresh", refreshToken = "refresh2")

        // 第一次 401，第二次（重放）200
        server.enqueue(MockResponse().setResponseCode(401).setBody("{\"detail\":\"expired\"}"))
        server.enqueue(MockResponse().setResponseCode(200).setBody("{\"ok\":true}"))

        val resp = call()
        assertEquals(200, resp.code)
        resp.close()

        val first = server.takeRequest()
        assertEquals("Bearer stale", first.getHeader("Authorization"))
        val retried = server.takeRequest()
        assertEquals("Bearer fresh", retried.getHeader("Authorization"))
        coVerify(exactly = 1) { authApi.refresh(any()) }
        coVerify { tokenStore.saveTokens("fresh", "refresh2") }
    }

    @Test
    fun `refresh 失败清 token 返回原 401`() {
        coEvery { tokenStore.accessToken() } returns "stale"
        coEvery { tokenStore.refreshToken() } returns "refresh1"
        coEvery { authApi.refresh(any()) } throws RuntimeException("refresh boom")

        server.enqueue(MockResponse().setResponseCode(401).setBody("{\"detail\":\"expired\"}"))

        val resp = call()
        assertEquals(401, resp.code)
        resp.close()

        coVerify { tokenStore.clear() }
    }

    @Test
    fun `无 refresh token 时 401 不刷新直接返回`() {
        coEvery { tokenStore.accessToken() } returns "stale"
        coEvery { tokenStore.refreshToken() } returns null

        server.enqueue(MockResponse().setResponseCode(401).setBody("{}"))

        val resp = call()
        assertEquals(401, resp.code)
        resp.close()

        coVerify(exactly = 0) { authApi.refresh(any()) }
    }
}
