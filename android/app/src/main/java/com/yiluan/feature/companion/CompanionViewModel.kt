package com.yiluan.feature.companion

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.companion.CompanionRepository
import com.yiluan.core.model.ApplyCompanionRequest
import com.yiluan.core.model.CompanionProfile
import com.yiluan.core.model.CompanionStats
import com.yiluan.core.model.Order
import com.yiluan.core.model.ServiceType
import com.yiluan.core.network.ApiError
import com.yiluan.core.order.OrderRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * 陪诊员流程 ViewModel：抢单/今日订单/接单动作/入驻/档案/统计。
 * ANDROID-DEV-B3-COMPANION — 对齐 iOS Companion Feature 后端交互序列。
 *
 * 接单前置门槛（后端 error_code）：
 *  PHONE_REQUIRED → 引导绑手机；VERIFICATION_REQUIRED → 提示等审核。
 */
@HiltViewModel
class CompanionViewModel @Inject constructor(
    private val orderRepository: OrderRepository,
    private val companionRepository: CompanionRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(CompanionUiState())
    val uiState: StateFlow<CompanionUiState> = _uiState.asStateFlow()

    // MARK: - 抢单大厅（available-orders = GET /orders?status=created）

    fun loadAvailableOrders() {
        _uiState.update { it.copy(isLoadingAvailable = true, availableError = false) }
        viewModelScope.launch {
            try {
                val orders = orderRepository.listOrders(status = "created")
                _uiState.update { it.copy(isLoadingAvailable = false, availableOrders = orders) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingAvailable = false, availableError = true) }
            }
        }
    }

    /** 接单：created→accepted。前置门槛失败按 error_code 引导。 */
    fun acceptOrder(orderId: String) {
        if (_uiState.value.actingOrderId != null) return
        _uiState.update { it.copy(actingOrderId = orderId, actionError = null) }
        viewModelScope.launch {
            try {
                orderRepository.acceptOrder(orderId)
                _uiState.update { it.copy(actingOrderId = null) }
                loadAvailableOrders() // 刷新大厅（该单已被接走）
            } catch (e: Exception) {
                val key = when (ApiError.codeOf(e)) {
                    "PHONE_REQUIRED" -> CompanionErrorKey.PHONE_REQUIRED
                    "VERIFICATION_REQUIRED" -> CompanionErrorKey.VERIFICATION_REQUIRED
                    else -> CompanionErrorKey.ACCEPT_FAILED
                }
                _uiState.update { it.copy(actingOrderId = null, actionError = key) }
            }
        }
    }

    // MARK: - 今日订单（GET /orders?status=accepted，客户端过滤今日）

    fun loadTodayOrders(today: String) {
        _uiState.update { it.copy(isLoadingToday = true, todayError = false) }
        viewModelScope.launch {
            try {
                val accepted = orderRepository.listOrders(status = "accepted")
                val todays = accepted.filter { it.appointmentDate.startsWith(today) }
                _uiState.update { it.copy(isLoadingToday = false, todayOrders = todays) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingToday = false, todayError = true) }
            }
        }
    }

    // MARK: - 订单动作（详情页：start/complete/reject）

    private fun runOrderAction(orderId: String, block: suspend () -> Order) {
        if (_uiState.value.actingOrderId != null) return
        _uiState.update { it.copy(actingOrderId = orderId, actionError = null) }
        viewModelScope.launch {
            try {
                val updated = block()
                _uiState.update { it.copy(actingOrderId = null, selectedOrder = updated) }
            } catch (e: Exception) {
                _uiState.update { it.copy(actingOrderId = null, actionError = CompanionErrorKey.ACTION_FAILED) }
            }
        }
    }

    fun startService(orderId: String) = runOrderAction(orderId) { orderRepository.startOrder(orderId) }
    fun completeService(orderId: String) = runOrderAction(orderId) { orderRepository.completeOrder(orderId) }
    fun rejectOrder(orderId: String) = runOrderAction(orderId) { orderRepository.rejectOrder(orderId) }

    fun loadOrderDetail(orderId: String) {
        viewModelScope.launch {
            try {
                val order = orderRepository.getOrder(orderId)
                _uiState.update { it.copy(selectedOrder = order) }
            } catch (e: Exception) {
                _uiState.update { it.copy(actionError = CompanionErrorKey.ACTION_FAILED) }
            }
        }
    }

    // MARK: - 入驻（POST /companions/apply）

    fun onApplyFieldChange(update: (CompanionApplyDraft) -> CompanionApplyDraft) {
        _uiState.update { it.copy(applyDraft = update(it.applyDraft), actionError = null) }
    }

    val canSubmitApply: Boolean
        get() = _uiState.value.applyDraft.let {
            it.realName.length in 2..50 && it.serviceTypes.isNotEmpty()
        }

    fun submitApply(onApplied: () -> Unit) {
        val draft = _uiState.value.applyDraft
        if (draft.realName.length !in 2..50 || draft.serviceTypes.isEmpty()) {
            _uiState.update { it.copy(actionError = CompanionErrorKey.APPLY_INVALID) }
            return
        }
        if (_uiState.value.isSubmittingApply) return
        _uiState.update { it.copy(isSubmittingApply = true, actionError = null) }
        viewModelScope.launch {
            try {
                val profile = companionRepository.apply(
                    ApplyCompanionRequest(
                        realName = draft.realName,
                        serviceTypes = draft.serviceTypes.joinToString(",") { it.value },
                        serviceArea = draft.serviceArea.takeIf { it.isNotBlank() },
                        idNumber = draft.idNumber.takeIf { it.isNotBlank() },
                        bio = draft.bio.takeIf { it.isNotBlank() },
                    ),
                )
                _uiState.update { it.copy(isSubmittingApply = false, myProfile = profile) }
                onApplied()
            } catch (e: Exception) {
                _uiState.update { it.copy(isSubmittingApply = false, actionError = CompanionErrorKey.APPLY_FAILED) }
            }
        }
    }

    // MARK: - 本人档案 + 统计

    fun loadMyProfile() {
        viewModelScope.launch {
            try {
                val p = companionRepository.myProfile()
                val s = companionRepository.myStats()
                _uiState.update { it.copy(myProfile = p, myStats = s) }
            } catch (e: Exception) {
                _uiState.update { it.copy(profileError = true) }
            }
        }
    }

    // MARK: - 公开陪诊员详情（患者视角）

    fun loadCompanionDetail(companionId: String) {
        _uiState.update { it.copy(isLoadingDetail = true, detailError = false) }
        viewModelScope.launch {
            try {
                val p = companionRepository.companionDetail(companionId)
                _uiState.update { it.copy(isLoadingDetail = false, viewedCompanion = p) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingDetail = false, detailError = true) }
            }
        }
    }

    fun clearActionError() {
        _uiState.update { it.copy(actionError = null) }
    }
}

/** 入驻草稿。 */
data class CompanionApplyDraft(
    val realName: String = "",
    val serviceTypes: Set<ServiceType> = emptySet(),
    val serviceArea: String = "",
    val idNumber: String = "",
    val bio: String = "",
)

/** 陪诊员错误 key（映射 i18n）。 */
enum class CompanionErrorKey {
    PHONE_REQUIRED, VERIFICATION_REQUIRED, ACCEPT_FAILED, ACTION_FAILED,
    APPLY_INVALID, APPLY_FAILED,
}

/** 陪诊员 UI 状态。 */
data class CompanionUiState(
    // 抢单大厅
    val availableOrders: List<Order> = emptyList(),
    val isLoadingAvailable: Boolean = false,
    val availableError: Boolean = false,
    // 今日订单
    val todayOrders: List<Order> = emptyList(),
    val isLoadingToday: Boolean = false,
    val todayError: Boolean = false,
    // 订单详情/动作
    val selectedOrder: Order? = null,
    val actingOrderId: String? = null,
    // 入驻
    val applyDraft: CompanionApplyDraft = CompanionApplyDraft(),
    val isSubmittingApply: Boolean = false,
    // 本人档案/统计
    val myProfile: CompanionProfile? = null,
    val myStats: CompanionStats? = null,
    val profileError: Boolean = false,
    // 公开详情
    val viewedCompanion: CompanionProfile? = null,
    val isLoadingDetail: Boolean = false,
    val detailError: Boolean = false,
    // 通用
    val actionError: CompanionErrorKey? = null,
)
