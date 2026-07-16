package com.yiluan.di

import android.content.Context
import androidx.datastore.core.DataStore
import androidx.datastore.preferences.core.Preferences
import androidx.datastore.preferences.preferencesDataStore
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

/**
 * 存储层 DI（ANDROID-BUG-B0-TEST-COVERAGE-GAP）。
 * 提供 token DataStore；TokenStore 注入它（原用 Context 扩展委托不可测，现可注入替身）。
 */
private val Context.tokenDataStore by preferencesDataStore(name = "yiluan_tokens")

@Module
@InstallIn(SingletonComponent::class)
object StorageModule {

    @Provides
    @Singleton
    fun provideTokenDataStore(
        @ApplicationContext context: Context,
    ): DataStore<Preferences> = context.tokenDataStore
}
