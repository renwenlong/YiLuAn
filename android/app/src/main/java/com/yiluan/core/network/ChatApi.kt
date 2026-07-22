package com.yiluan.core.network

import com.yiluan.core.model.ChatBackfillResponse
import com.yiluan.core.model.ChatMessage
import com.yiluan.core.model.ChatMessageListResponse
import com.yiluan.core.model.MarkReadResponse
import com.yiluan.core.model.SendChatMessageRequest
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * 聊天 REST API（需登录）。ANDROID-DEV-B4-REALTIME。
 * 一订单一会话，orderId 为路径参数。WS 主发，REST 兜底 + 历史 + backfill。
 */
interface ChatApi {
    /** 消息历史（分页，默认 page_size=50）。 */
    @GET("chats/{orderId}/messages")
    suspend fun messages(
        @Path("orderId") orderId: String,
        @Query("page") page: Int,
        @Query("page_size") pageSize: Int,
    ): ChatMessageListResponse

    /**
     * 断线增量回灌（AC3 不丢消息）：after_id 之后的消息，升序。
     * after_id 可空(全量)；has_more=true 用 next_after_id 续拉。
     */
    @GET("chats/{orderId}/messages/backfill")
    suspend fun backfill(
        @Path("orderId") orderId: String,
        @Query("after_id") afterId: String?,
        @Query("limit") limit: Int,
    ): ChatBackfillResponse

    /** 发消息（HTTP 兜底，WS 失败时降级）。 */
    @POST("chats/{orderId}/messages")
    suspend fun send(
        @Path("orderId") orderId: String,
        @Body body: SendChatMessageRequest,
    ): ChatMessage

    /** 标记会话已读。 */
    @POST("chats/{orderId}/read")
    suspend fun markRead(@Path("orderId") orderId: String): MarkReadResponse
}
