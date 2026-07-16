package com.yiluan.core.storage

import android.content.Context
import android.content.SharedPreferences
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import dagger.hilt.android.qualifiers.ApplicationContext
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 家属 share_session JWT 存储（EncryptedSharedPreferences）。
 * ANDROID-DEV-B0-CORE — 对齐 iOS ShareSessionStore（Keychain）。
 *
 * 与本人 token 严格隔离：share_session 是访客态凭证（30min TTL），绝不与
 * 本人 access token 混存。加密落盘防泄漏（对齐 iOS Keychain 语义）。
 */
@Singleton
class ShareSessionStore @Inject constructor(
    @ApplicationContext context: Context,
) {
    private val prefs: SharedPreferences by lazy {
        val masterKey = MasterKey.Builder(context)
            .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
            .build()
        EncryptedSharedPreferences.create(
            context,
            "yiluan_share_session",
            masterKey,
            EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM,
        )
    }

    fun save(session: String, expiresAtMillis: Long) {
        prefs.edit()
            .putString(KEY_SESSION, session)
            .putLong(KEY_EXPIRES_AT, expiresAtMillis)
            .apply()
    }

    fun session(): String? = prefs.getString(KEY_SESSION, null)

    fun expiresAtMillis(): Long = prefs.getLong(KEY_EXPIRES_AT, 0L)

    fun isExpired(nowMillis: Long = System.currentTimeMillis()): Boolean {
        return isExpired(session(), expiresAtMillis(), nowMillis)
    }

    fun clear() {
        prefs.edit().clear().apply()
    }

    companion object {
        private const val KEY_SESSION = "share_session"
        private const val KEY_EXPIRES_AT = "share_session_expires_at" // epoch millis

        /**
         * 过期判断纯函数（可 JVM 单测，不依赖 EncryptedSharedPreferences）。
         * session 空 / 无到期时间 / 已过期 → true。
         */
        fun isExpired(session: String?, expiresAtMillis: Long, nowMillis: Long): Boolean {
            return session.isNullOrEmpty() || expiresAtMillis <= 0L || expiresAtMillis <= nowMillis
        }
    }
}
