package com.yiluan.core.storage

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.tokenDataStore by preferencesDataStore(name = "yiluan_tokens")

/**
 * 本人 access/refresh token 存储（DataStore）。
 * ANDROID-DEV-B0-CORE — 对齐 iOS TokenStore 语义。
 *
 * access token 供 AuthInterceptor 注入 Authorization；refresh token 供 401 刷新链路。
 * 注：access token 非最高敏感（30min 过期），DataStore 足够；share_session 走 Encrypted 存储。
 */
@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext private val context: Context,
) {
    private object Keys {
        val ACCESS = stringPreferencesKey("access_token")
        val REFRESH = stringPreferencesKey("refresh_token")
    }

    val accessTokenFlow: Flow<String?> =
        context.tokenDataStore.data.map { it[Keys.ACCESS] }

    val refreshTokenFlow: Flow<String?> =
        context.tokenDataStore.data.map { it[Keys.REFRESH] }

    /** 同步读 access token（拦截器在 OkHttp 线程需即时值，用 runBlocking 桥接调用方决定）。 */
    suspend fun accessToken(): String? = context.tokenDataStore.data.first()[Keys.ACCESS]

    suspend fun refreshToken(): String? = context.tokenDataStore.data.first()[Keys.REFRESH]

    suspend fun saveTokens(access: String, refresh: String) {
        context.tokenDataStore.edit {
            it[Keys.ACCESS] = access
            it[Keys.REFRESH] = refresh
        }
    }

    suspend fun updateAccessToken(access: String) {
        context.tokenDataStore.edit { it[Keys.ACCESS] = access }
    }

    suspend fun clear() {
        context.tokenDataStore.edit { it.clear() }
    }
}
