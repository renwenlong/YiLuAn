package com.yiluan.core.network

import com.yiluan.core.model.MarkReadResponse
import com.yiluan.core.model.NotificationListResponse
import com.yiluan.core.model.UnreadCountResponse
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * 通知 REST API（需登录）。ANDROID-DEV-B4-REALTIME。
 * WS 前台推 + REST 列表兜底（一期不含 FCM 离线）。
 */
interface NotificationApi {
    /** 通知列表（兜底，倒序，默认 page_size=20）。 */
    @GET("notifications")
    suspend fun list(
        @Query("page") page: Int,
        @Query("page_size") pageSize: Int,
    ): NotificationListResponse

    /** 未读数。 */
    @GET("notifications/unread-count")
    suspend fun unreadCount(): UnreadCountResponse

    /** 标单条已读。 */
    @POST("notifications/{notificationId}/read")
    suspend fun markRead(@Path("notificationId") notificationId: String): MarkReadResponse

    /** 全部已读。 */
    @POST("notifications/read-all")
    suspend fun markAllRead(): MarkReadResponse
}
