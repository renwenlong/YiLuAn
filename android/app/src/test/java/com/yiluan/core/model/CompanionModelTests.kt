package com.yiluan.core.model

import com.yiluan.core.network.ApiError
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import retrofit2.HttpException
import retrofit2.Response

/**
 * Companion 模型计算属性 + ApiError 解析单测（ANDROID-DEV-B3-COMPANION）。
 */
class CompanionModelTests {

    @Test
    fun `serviceTypeList 逗号拆分`() {
        val p = CompanionProfile(id = "c1", serviceTypes = "full_accompany, errand")
        assertEquals(listOf("full_accompany", "errand"), p.serviceTypeList)
    }

    @Test
    fun `isVerified 仅 verified 为真`() {
        assertTrue(CompanionProfile(id = "c1", verificationStatus = "verified").isVerified)
        assertFalse(CompanionProfile(id = "c1", verificationStatus = "pending").isVerified)
    }

    @Test
    fun `displayName 优先化名`() {
        assertEquals("张**", CompanionProfile(id = "c1", pseudonymName = "张**", realName = "张三").displayName)
        assertEquals("张三", CompanionProfile(id = "c1", realName = "张三").displayName)
        assertEquals("", CompanionProfile(id = "c1").displayName)
    }

    @Test
    fun `ApiError 解析 detail code`() {
        val body = """{"detail":{"code":"PHONE_REQUIRED","message":"x"}}"""
            .toResponseBody("application/json".toMediaType())
        val e = HttpException(Response.error<Any>(400, body))
        assertEquals("PHONE_REQUIRED", ApiError.codeOf(e))
    }

    @Test
    fun `ApiError 非 HttpException 返回 null`() {
        assertNull(ApiError.codeOf(RuntimeException("net")))
    }

    @Test
    fun `ApiError detail 为字符串时返回 null 不崩`() {
        val body = """{"detail":"plain string error"}"""
            .toResponseBody("application/json".toMediaType())
        val e = HttpException(Response.error<Any>(400, body))
        assertNull(ApiError.codeOf(e))
    }
}
