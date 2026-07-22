package com.yiluan.feature.chat

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.model.ChatMessage
import com.yiluan.core.realtime.ChatRepository
import com.yiluan.core.realtime.ChatSocket
import com.yiluan.core.realtime.ChatSocketEvent
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
 * 聊天室 ViewModel：REST 首屏历史 + WS 实时收发 + 断线 backfill(AC3) + 已读。
 * ANDROID-DEV-B4-REALTIME — 对齐 iOS ChatViewModel（并补 backfill 缺口）。
 */
@HiltViewModel
class ChatViewModel @Inject constructor(
    private val repository: ChatRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ChatUiState())
    val uiState: StateFlow<ChatUiState> = _uiState.asStateFlow()

    private var socket: ChatSocket? = null
    private var orderId: String = ""

    /** 进入聊天室：拉历史 + 建 WS。 */
    fun enter(orderId: String) {
        this.orderId = orderId
        loadHistory()
        val s = repository.createSocket(orderId, viewModelScope)
        socket = s
        s.events.onEach { ev ->
            when (ev) {
                is ChatSocketEvent.Message -> appendMessage(ev.message)
                is ChatSocketEvent.Reconnected -> backfill() // AC3 补偿
                is ChatSocketEvent.Closed -> _uiState.update { it.copy(connected = false) }
            }
        }.launchIn(viewModelScope)
        s.connect()
    }

    private fun loadHistory() {
        _uiState.update { it.copy(isLoading = true, error = false) }
        viewModelScope.launch {
            try {
                val msgs = repository.history(orderId)
                _uiState.update { it.copy(isLoading = false, messages = dedupSorted(msgs)) }
                markRead()
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoading = false, error = true) }
            }
        }
    }

    /** 断线重连后增量回灌，从本地最后一条 id 之后拉。 */
    private fun backfill() {
        val lastId = _uiState.value.messages.lastOrNull()?.id
        viewModelScope.launch {
            try {
                val missed = repository.backfill(orderId, afterId = lastId)
                if (missed.isNotEmpty()) {
                    _uiState.update { it.copy(messages = dedupSorted(it.messages + missed), connected = true) }
                } else {
                    _uiState.update { it.copy(connected = true) }
                }
            } catch (_: Exception) {
                // 兜底失败不崩，等下次事件
            }
        }
    }

    private fun appendMessage(msg: ChatMessage) {
        _uiState.update { it.copy(messages = dedupSorted(it.messages + msg), connected = true) }
    }

    fun onInputChange(text: String) {
        _uiState.update { it.copy(input = text.take(4000)) }
    }

    /** 发消息：WS 主，失败降级 REST。 */
    fun send() {
        val content = _uiState.value.input.trim()
        if (content.isEmpty()) return
        _uiState.update { it.copy(input = "") }
        val sentViaWs = socket?.sendMessage(type = "text", content = content) ?: false
        if (!sentViaWs) {
            viewModelScope.launch {
                try {
                    val msg = repository.sendViaRest(orderId, content)
                    appendMessage(msg)
                } catch (e: Exception) {
                    _uiState.update { it.copy(error = true) }
                }
            }
        }
        // WS 发出后，服务端会广播回该消息帧(含 id)，由 appendMessage 去重插入。
    }

    private fun markRead() {
        viewModelScope.launch {
            try {
                repository.markRead(orderId)
            } catch (_: Exception) {
            }
        }
    }

    /** 按 id 去重 + 按 created_at 排序（WS/backfill/REST 可能重叠）。 */
    private fun dedupSorted(list: List<ChatMessage>): List<ChatMessage> =
        list.distinctBy { it.id }.sortedBy { it.createdAt ?: "" }

    override fun onCleared() {
        socket?.disconnect()
        super.onCleared()
    }
}

data class ChatUiState(
    val messages: List<ChatMessage> = emptyList(),
    val input: String = "",
    val isLoading: Boolean = false,
    val connected: Boolean = false,
    val error: Boolean = false,
)
