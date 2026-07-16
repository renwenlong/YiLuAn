package com.yiluan.core.storage

import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * ShareSessionStore.isExpired 纯函数单测（ANDROID-DEV-B0-CORE）。
 * 只测无副作用的过期判断逻辑，不依赖 EncryptedSharedPreferences（那部分需 instrumentation）。
 */
class ShareSessionStoreTest {

    private val now = 1_000_000L

    @Test
    fun `session 为 null 视为过期`() {
        assertTrue(ShareSessionStore.isExpired(null, now + 60_000, now))
    }

    @Test
    fun `session 为空串视为过期`() {
        assertTrue(ShareSessionStore.isExpired("", now + 60_000, now))
    }

    @Test
    fun `无到期时间(0)视为过期`() {
        assertTrue(ShareSessionStore.isExpired("jwt", 0L, now))
    }

    @Test
    fun `到期时间已过视为过期`() {
        assertTrue(ShareSessionStore.isExpired("jwt", now - 1, now))
    }

    @Test
    fun `到期时间等于当前视为过期(边界)`() {
        assertTrue(ShareSessionStore.isExpired("jwt", now, now))
    }

    @Test
    fun `有效 session 且未到期不过期`() {
        assertFalse(ShareSessionStore.isExpired("jwt", now + 60_000, now))
    }
}
