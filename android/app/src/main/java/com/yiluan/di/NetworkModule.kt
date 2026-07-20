package com.yiluan.di

import com.yiluan.BuildConfig
import com.yiluan.core.network.ApiEndpoint
import com.yiluan.core.network.AuthApi
import com.yiluan.core.network.AuthInterceptor
import com.yiluan.core.network.EmergencyContactApi
import com.yiluan.core.network.FamilyMemberApi
import com.yiluan.core.network.FollowupReminderApi
import com.yiluan.core.network.HospitalApi
import com.yiluan.core.network.OrderApi
import com.yiluan.core.network.ReviewApi
import com.yiluan.core.network.UserApi
import com.yiluan.core.network.WalletApi
import com.jakewharton.retrofit2.converter.kotlinx.serialization.asConverterFactory
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import kotlinx.serialization.json.Json
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import retrofit2.Retrofit
import javax.inject.Named
import javax.inject.Singleton

/**
 * 网络层 DI（design §1§2）。
 * ANDROID-DEV-B0-CORE — 装配 OkHttp/Retrofit/ApiEndpoint/AuthApi。
 *
 * 关键：AuthApi 用**裸 OkHttp**（无 AuthInterceptor），供 401 刷新链路，防递归。
 * 业务 Retrofit 挂 AuthInterceptor。两者共享底层连接池以省资源。
 */
@Module
@InstallIn(SingletonComponent::class)
object NetworkModule {

    @Provides
    @Singleton
    fun provideJson(): Json = Json {
        ignoreUnknownKeys = true
        explicitNulls = false
        coerceInputValues = true
    }

    @Provides
    @Singleton
    fun provideLoggingInterceptor(): HttpLoggingInterceptor =
        HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) {
                HttpLoggingInterceptor.Level.BODY
            } else {
                HttpLoggingInterceptor.Level.NONE
            }
        }

    /** 裸 OkHttp（无 AuthInterceptor），供 AuthApi 刷新 + WS 复用。 */
    @Provides
    @Singleton
    @Named("bare")
    fun provideBareOkHttp(logging: HttpLoggingInterceptor): OkHttpClient =
        OkHttpClient.Builder()
            .addInterceptor(logging)
            .build()

    /** 业务 OkHttp（挂 AuthInterceptor）。 */
    @Provides
    @Singleton
    @Named("authed")
    fun provideAuthedOkHttp(
        @Named("bare") bare: OkHttpClient,
        authInterceptor: AuthInterceptor,
    ): OkHttpClient =
        bare.newBuilder()
            .addInterceptor(authInterceptor)
            .build()

    /** WS 复用裸 OkHttp（认证靠 query 参数，不需 AuthInterceptor）。 */
    @Provides
    @Singleton
    fun provideWsOkHttp(@Named("bare") bare: OkHttpClient): OkHttpClient = bare

    @Provides
    @Singleton
    @Named("bare")
    fun provideBareRetrofit(
        @Named("bare") client: OkHttpClient,
        json: Json,
    ): Retrofit = buildRetrofit(client, json)

    @Provides
    @Singleton
    @Named("authed")
    fun provideAuthedRetrofit(
        @Named("authed") client: OkHttpClient,
        json: Json,
    ): Retrofit = buildRetrofit(client, json)

    private fun buildRetrofit(client: OkHttpClient, json: Json): Retrofit =
        Retrofit.Builder()
            .baseUrl(BuildConfig.API_BASE_URL)
            .client(client)
            .addConverterFactory(json.asConverterFactory("application/json".toMediaType()))
            .build()

    @Provides
    @Singleton
    fun provideAuthApi(@Named("bare") retrofit: Retrofit): AuthApi =
        retrofit.create(AuthApi::class.java)

    @Provides
    @Singleton
    fun provideApiEndpoint(@Named("authed") retrofit: Retrofit): ApiEndpoint =
        retrofit.create(ApiEndpoint::class.java)

    /** 用户 API 需登录态，走挂 AuthInterceptor 的业务 Retrofit。 */
    @Provides
    @Singleton
    fun provideUserApi(@Named("authed") retrofit: Retrofit): UserApi =
        retrofit.create(UserApi::class.java)

    /** 订单 API（需登录）。 */
    @Provides
    @Singleton
    fun provideOrderApi(@Named("authed") retrofit: Retrofit): OrderApi =
        retrofit.create(OrderApi::class.java)

    /** 医院 API（需登录）。 */
    @Provides
    @Singleton
    fun provideHospitalApi(@Named("authed") retrofit: Retrofit): HospitalApi =
        retrofit.create(HospitalApi::class.java)

    // ── B6 长尾 API（均 authed）──
    @Provides
    @Singleton
    fun provideFamilyMemberApi(@Named("authed") retrofit: Retrofit): FamilyMemberApi =
        retrofit.create(FamilyMemberApi::class.java)

    @Provides
    @Singleton
    fun provideEmergencyContactApi(@Named("authed") retrofit: Retrofit): EmergencyContactApi =
        retrofit.create(EmergencyContactApi::class.java)

    @Provides
    @Singleton
    fun provideWalletApi(@Named("authed") retrofit: Retrofit): WalletApi =
        retrofit.create(WalletApi::class.java)

    @Provides
    @Singleton
    fun provideReviewApi(@Named("authed") retrofit: Retrofit): ReviewApi =
        retrofit.create(ReviewApi::class.java)

    @Provides
    @Singleton
    fun provideFollowupReminderApi(@Named("authed") retrofit: Retrofit): FollowupReminderApi =
        retrofit.create(FollowupReminderApi::class.java)
}
