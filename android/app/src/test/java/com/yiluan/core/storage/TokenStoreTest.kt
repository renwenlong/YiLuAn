package com.yiluan.core.storage

import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.core.PreferenceDataStoreFactory
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.test.runTest
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import java.io.File

/**
 * TokenStore 单测（ANDROID-BUG-B0-TEST-COVERAGE-GAP AC4: TokenStore 存取）。
 * 用真实 DataStore（临时文件）跑 JVM 单测，验 save/read/update/clear 语义。
 */
class TokenStoreTest {

    private lateinit var tmpFile: File
    private lateinit var scope: CoroutineScope
    private lateinit var dataStore: DataStore<Preferences>
    private lateinit var store: TokenStore

    @Before
    fun setup() {
        tmpFile = File.createTempFile("token_test", ".preferences_pb")
        tmpFile.delete()
        scope = CoroutineScope(SupervisorJob() + Dispatchers.Unconfined)
        dataStore = PreferenceDataStoreFactory.create(scope = scope) { tmpFile }
        store = TokenStore(dataStore)
    }

    @After
    fun teardown() {
        scope.cancel()
        tmpFile.delete()
    }

    @Test
    fun `初始无 token 时读取为 null`() = runTest {
        assertNull(store.accessToken())
        assertNull(store.refreshToken())
    }

    @Test
    fun `saveTokens 后可读回 access 和 refresh`() = runTest {
        store.saveTokens(access = "acc1", refresh = "ref1")
        assertEquals("acc1", store.accessToken())
        assertEquals("ref1", store.refreshToken())
    }

    @Test
    fun `updateAccessToken 只改 access 不动 refresh`() = runTest {
        store.saveTokens(access = "acc1", refresh = "ref1")
        store.updateAccessToken("acc2")
        assertEquals("acc2", store.accessToken())
        assertEquals("ref1", store.refreshToken())
    }

    @Test
    fun `clear 后 token 全部清空`() = runTest {
        store.saveTokens(access = "acc1", refresh = "ref1")
        store.clear()
        assertNull(store.accessToken())
        assertNull(store.refreshToken())
    }

    @Test
    fun `accessTokenFlow 反映最新值`() = runTest {
        store.saveTokens(access = "accFlow", refresh = "r")
        assertEquals("accFlow", kotlinx.coroutines.flow.first(store.accessTokenFlow))
    }
}
