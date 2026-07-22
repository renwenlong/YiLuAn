package com.yiluan.core.realtime

import com.yiluan.core.model.Notification
import com.yiluan.core.network.NotificationApi
import com.yiluan.core.network.WebSocketClient
import com.yiluan.core.storage.TokenStore
import kotlinx.coroutines.CoroutineScope
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 通知仓库：REST 列表/未读数/已读 + NotificationSocket 工厂。
 * ANDROID-DEV-B4-REALTIME。
 */
@Singleton
class NotificationRepository @Inject constructor(
    private val notificationApi: NotificationApi,
    private val wsClient: WebSocketClient,
    private val tokenStore: TokenStore,
) {
    suspend fun list(page: Int = 1): List<Notification> =
        notificationApi.list(page = page, pageSize = 20).items

    suspend fun unreadCount(): Int = notificationApi.unreadCount().count

    suspend fun markRead(id: String): Int = notificationApi.markRead(id).markedRead

    suspend fun markAllRead(): Int = notificationApi.markAllRead().markedRead

    /** 创建 NotificationSocket（scope 由 ViewModel 传）。 */
    fun createSocket(scope: CoroutineScope): NotificationSocket =
        NotificationSocket(wsClient = wsClient, tokenStore = tokenStore, scope = scope)
}
