package com.yiluan.feature.precheck

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.model.OrderPrecheckSummary
import com.yiluan.core.precheck.PrecheckRepository
import com.yiluan.core.realtime.PrecheckSocket
import com.yiluan.core.realtime.PrecheckSocketEvent
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.launchIn
import kotlinx.coroutines.flow.onEach
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import retrofit2.HttpException
import javax.inject.Inject

/**
 * Precheck 4 信任卡 ViewModel：HTTP summary + WS 推送刷新 + 轮询兜底。
 * ANDROID-DEV-B5-PRECHECK-SHARE。
 *
 * 兜底逻辑（任务口径）：WS 首连 5s 未 auth_ok → 轮询(间隔 3s, 最多 10 次)；
 * WS auth_ok → 停轮询；WS event → 重拉 HTTP summary；永久 close → 报错。
 * 404(历史订单无信任卡) 不阻断，summary 留 null。
 */
@HiltViewModel
class PrecheckViewModel @Inject constructor(
    private val repository: PrecheckRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(PrecheckUiState())
    val uiState: StateFlow<PrecheckUiState> = _uiState.asStateFlow()

    private var socket: PrecheckSocket? = null
    private var pollJob: Job? = null
    private var orderId: String = ""

    fun enter(orderId: String) {
        this.orderId = orderId
        refreshSummary()
        val s = repository.createSocket(orderId, viewModelScope)
        socket = s
        s.events.onEach { ev ->
            when (ev) {
                is PrecheckSocketEvent.Connected -> stopPolling() // WS 就绪停轮询
                is PrecheckSocketEvent.Invalidated -> refreshSummary()
                is PrecheckSocketEvent.NeedPolling -> startPolling()
                is PrecheckSocketEvent.Error -> _uiState.update { it.copy(wsError = ev.closeCode) }
            }
        }.launchIn(viewModelScope)
        s.connect()
    }

    private fun refreshSummary() {
        viewModelScope.launch {
            try {
                val summary = repository.summary(orderId)
                _uiState.update { it.copy(summary = summary, notFound = false, loadError = false) }
            } catch (e: HttpException) {
                if (e.code() == 404) {
                    // 历史订单无信任卡记录 → 不阻断付款
                    _uiState.update { it.copy(notFound = true, summary = null) }
                } else {
                    _uiState.update { it.copy(loadError = true) }
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(loadError = true) }
            }
        }
    }

    /** 轮询兜底：间隔 3s，最多 10 次。 */
    private fun startPolling() {
        if (pollJob?.isActive == true) return
        pollJob = viewModelScope.launch {
            var attempts = 0
            while (attempts < MAX_POLL) {
                delay(POLL_INTERVAL_MS)
                refreshSummary()
                attempts++
                if (_uiState.value.summary?.allReady == true) break
            }
        }
    }

    private fun stopPolling() {
        pollJob?.cancel()
        pollJob = null
    }

    override fun onCleared() {
        socket?.disconnect()
        stopPolling()
        super.onCleared()
    }

    private companion object {
        const val POLL_INTERVAL_MS = 3_000L
        const val MAX_POLL = 10
    }
}

data class PrecheckUiState(
    val summary: OrderPrecheckSummary? = null,
    val notFound: Boolean = false,
    val loadError: Boolean = false,
    val wsError: Int? = null,
)
