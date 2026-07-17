package com.yiluan.core.storage

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 本人 access/refresh token 存储（DataStore）。
 * ANDROID-DEV-B0-CORE — 对齐 iOS TokenStore 语义。
 * ANDROID-BUG-B0-TEST-COVERAGE-GAP — 重构为注入 DataStore<Preferences>（原用
 * Context 扩展委托，JVM 不可测）；DataStore 由 StorageModule 提供，测试可注入临时文件实例。
 *
 * access token 供 AuthInterceptor 注入 Authorization；refresh token 供 401 刷新链路。
 * 注：access token 非最高敏感（30min 过期），DataStore 足够；share_session 走 Encrypted 存储。
 */
@Singleton
class TokenStore @Inject constructor(
    private val dataStore: DataStore<Preferences>,
) {
    private object Keys {
        val ACCESS = stringPreferencesKey("access_token")
        val REFRESH = stringPreferencesKey("refresh_token")
    }

    val accessTokenFlow: Flow<String?> =
        dataStore.data.map { it[Keys.ACCESS] }

    val refreshTokenFlow: Flow<String?> =
        dataStore.data.map { it[Keys.REFRESH] }

    suspend fun accessToken(): String? = dataStore.data.first()[Keys.ACCESS]

    suspend fun refreshToken(): String? = dataStore.data.first()[Keys.REFRESH]

    suspend fun saveTokens(access: String, refresh: String) {
        dataStore.edit {
            it[Keys.ACCESS] = access
            it[Keys.REFRESH] = refresh
        }
    }

    suspend fun updateAccessToken(access: String) {
        dataStore.edit { it[Keys.ACCESS] = access }
    }

    suspend fun clear() {
        dataStore.edit { it.clear() }
    }
}
