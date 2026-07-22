package com.yiluan.feature.notification

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.model.Notification
import com.yiluan.core.realtime.NotificationRepository
import com.yiluan.core.realtime.NotificationSocket
import com.yiluan.core.realtime.NotificationSocketEvent
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * 通知 ViewModel：REST 列表兜底 + WS 前台推 + 未读数 + 标已读。
 * ANDROID-DEV-B4-REALTIME — 对齐 iOS NotificationViewModel。
 */
@HiltViewModel
class NotificationViewModel @Inject constructor(
    private val repository: NotificationRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(NotificationUiState())
    val uiState: StateFlow<NotificationUiState> = _uiState.asStateFlow()

    private var socket: NotificationSocket? = null

    fun enter() {
        loadList()
        loadUnread()
        val s = repository.createSocket(viewModelScope)
        socket = s
        s.events.onEach { ev ->
            when (ev) {
                is NotificationSocketEvent.NewNotification -> prepend(ev.notification)
                is NotificationSocketEvent.UnreadCount -> _uiState.update { it.copy(unreadCount = ev.count) }
            }
        }.launchIn(viewModelScope)
        s.connect()
    }

    private fun loadList() {
        _uiState.update { it.copy(isLoading = true, error = false) }
        viewModelScope.launch {
            try {
                val list = repository.list()
                _uiState.update { it.copy(isLoading = false, notifications = list) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, error = true) }
            }
        }
    }

    private fun loadUnread() {
        viewModelScope.launch {
            try {
                val n = repository.unreadCount()
                _uiState.update { it.copy(unreadCount = n) }
            } catch (_: Exception) {
            }
        }
    }

    private fun prepend(n: Notification) {
        _uiState.update {
            if (it.notifications.any { x -> x.id == n.id }) it
            else it.copy(notifications = listOf(n) + it.notifications)
        }
    }

    fun markRead(id: String) {
        viewModelScope.launch {
            try {
                repository.markRead(id)
                _uiState.update { st ->
                    st.copy(
                        notifications = st.notifications.map { if (it.id == id) it.copy(isRead = true) else it },
                        unreadCount = (st.unreadCount - 1).coerceAtLeast(0),
                    )
                }
            } catch (_: Exception) {
            }
        }
    }

    fun markAllRead() {
        viewModelScope.launch {
            try {
                repository.markAllRead()
                _uiState.update { st ->
                    st.copy(
                        notifications = st.notifications.map { it.copy(isRead = true) },
                        unreadCount = 0,
                    )
                }
            } catch (_: Exception) {
            }
        }
    }

    override fun onCleared() {
        socket?.disconnect()
        super.onCleared()
    }
}

data class NotificationUiState(
    val notifications: List<Notification> = emptyList(),
    val unreadCount: Int = 0,
    val isLoading: Boolean = false,
    val error: Boolean = false,
)
