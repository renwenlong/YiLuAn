package com.yiluan.core.network

import retrofit2.http.GET

/**
 * 业务 API 契约（对齐 openapi.json，手工映射，见 design §1）。
 * ANDROID-DEV-B0-CORE — B0 骨架仅放健康探针验证网络层贯通；
 * 各 Feature 的 endpoint 在对应批次（B1-B6）扩充，保持与 iOS APIEndpoint 对齐。
 */
interface ApiEndpoint {

    /** 就绪探针（DB+Redis 双探活），用于 B0 网络层贯通冒烟。 */
    @GET("readiness")
    suspend fun readiness(): Map<String, String>
}
