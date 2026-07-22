package com.yiluan.core.network

import com.yiluan.core.model.OrderPrecheckSummary
import retrofit2.http.GET
import retrofit2.http.Path

/**
 * Precheck API（需登录，患者本人）。ANDROID-DEV-B5-PRECHECK-SHARE。
 * 单 endpoint 一次拉全 4 信任卡；WS event 仅 invalidate 信号 → 重调此接口拉最新 summary。
 * 404 = 历史订单无信任卡记录（不阻断付款，上层处理）。
 */
interface PrecheckApi {
    @GET("users/orders/{orderId}/precheck-status")
    suspend fun precheckStatus(@Path("orderId") orderId: String): OrderPrecheckSummary
}
