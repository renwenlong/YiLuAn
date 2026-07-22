package com.yiluan.core.precheck

import com.yiluan.core.model.OrderPrecheckSummary
import com.yiluan.core.network.PrecheckApi
import com.yiluan.core.network.WebSocketClient
import com.yiluan.core.realtime.PrecheckSocket
import com.yiluan.core.storage.TokenStore
import kotlinx.coroutines.CoroutineScope
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Precheck 仓库：4 信任卡 summary + PrecheckSocket 工厂。
 * ANDROID-DEV-B5-PRECHECK-SHARE。
 */
@Singleton
class PrecheckRepository @Inject constructor(
    private val precheckApi: PrecheckApi,
    private val wsClient: WebSocketClient,
    private val tokenStore: TokenStore,
) {
    /** 拉最新 4 信任卡 summary。404(历史订单) 由上层 catch 处理，不阻断付款。 */
    suspend fun summary(orderId: String): OrderPrecheckSummary =
        precheckApi.precheckStatus(orderId)

    fun createSocket(orderId: String, scope: CoroutineScope): PrecheckSocket =
        PrecheckSocket(orderId = orderId, wsClient = wsClient, tokenStore = tokenStore, scope = scope)
}
