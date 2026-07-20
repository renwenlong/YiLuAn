package com.yiluan.core.network

import com.yiluan.core.model.CreateFollowupReminderRequest
import com.yiluan.core.model.FollowupReminder
import com.yiluan.core.model.FollowupReminderListResponse
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * 复诊提醒 API（需登录）。ANDROID-DEV-B6-LONGTAIL。
 * 注意: list/delete 路径是 orders/me/followup-reminders（非 users/me/...）。
 * 仅 order=completed/reviewed 可建；仅 pending 可删。
 */
interface FollowupReminderApi {
    @POST("orders/{orderId}/followup-reminders")
    suspend fun create(
        @Path("orderId") orderId: String,
        @Body body: CreateFollowupReminderRequest,
    ): FollowupReminder

    @GET("orders/me/followup-reminders")
    suspend fun list(): FollowupReminderListResponse

    @DELETE("orders/me/followup-reminders/{reminderId}")
    suspend fun delete(@Path("reminderId") reminderId: String)
}
