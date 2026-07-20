package com.yiluan.core.realtime

import com.yiluan.core.model.ChatMessage
import com.yiluan.core.model.SendChatMessageRequest
import com.yiluan.core.network.ChatApi
import com.yiluan.core.network.WebSocketClient
import com.yiluan.core.storage.TokenStore
import kotlinx.coroutines.CoroutineScope
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 聊天仓库：REST 历史/backfill/发送/已读 + ChatSocket 工厂。
 * ANDROID-DEV-B4-REALTIME — 对齐后端 WS/REST 契约。
 *
 * AC3 不丢消息：重连后 backfill(after_id=本地 lastId) 增量回灌，has_more 续拉。
 */
@Singleton
class ChatRepository @Inject constructor(
    private val chatApi: ChatApi,
    private val wsClient: WebSocketClient,
    private val tokenStore: TokenStore,
) {
    /** 首屏历史（分页，默认 50）。 */
    suspend fun history(orderId: String, page: Int = 1): List<ChatMessage> =
        chatApi.messages(orderId, page = page, pageSize = 50).items

    /**
     * 断线增量回灌：从 afterId 之后拉全部（has_more 续拉），保证不丢。
     * afterId=null 时全量。
     */
    suspend fun backfill(orderId: String, afterId: String?): List<ChatMessage> {
        val all = mutableListOf<ChatMessage>()
        var cursor = afterId
        var more: Boolean
        do {
            val resp = chatApi.backfill(orderId, afterId = cursor, limit = 100)
            all += resp.items
            cursor = resp.nextAfterId
            more = resp.hasMore
        } while (more && cursor != null)
        return all
    }

    /** REST 发消息（WS 失败降级）。 */
    suspend fun sendViaRest(orderId: String, content: String, type: String = "text"): ChatMessage =
        chatApi.send(orderId, SendChatMessageRequest(content = content, type = type))

    /** 标会话已读。 */
    suspend fun markRead(orderId: String): Int = chatApi.markRead(orderId).markedRead

    /** 创建该订单的 ChatSocket（scope 由 ViewModel 传 viewModelScope）。 */
    fun createSocket(orderId: String, scope: CoroutineScope): ChatSocket =
        ChatSocket(orderId = orderId, wsClient = wsClient, tokenStore = tokenStore, scope = scope)
}
