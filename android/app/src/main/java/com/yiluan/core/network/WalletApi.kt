package com.yiluan.core.network

import com.yiluan.core.model.TransactionListResponse
import com.yiluan.core.model.WalletSummary
import retrofit2.http.GET
import retrofit2.http.Query

/**
 * 钱包 API（需登录）。ANDROID-DEV-B6-LONGTAIL。
 */
interface WalletApi {
    @GET("wallet")
    suspend fun summary(): WalletSummary

    @GET("wallet/transactions")
    suspend fun transactions(
        @Query("page") page: Int,
        @Query("page_size") pageSize: Int,
    ): TransactionListResponse
}
