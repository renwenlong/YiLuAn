package com.yiluan.feature.order

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.model.CreateOrderRequest
import com.yiluan.core.model.Hospital
import com.yiluan.core.model.Order
import com.yiluan.core.model.ServiceType
import com.yiluan.core.order.HospitalRepository
import com.yiluan.core.order.OrderRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * 订单流程 ViewModel：列表 / 详情 / 下单 / 支付。
 * ANDROID-DEV-B2-PATIENT — 对齐 iOS OrderViewModel 后端交互序列。
 *
 * 支付（ADR-0041 解耦）：payOrder → mock 成功 → 复查 payment_state=paid，
 * 业务 status 仍 created（待陪诊师接单），pay-result 展示成功/失败。
 */
@HiltViewModel
class OrderViewModel @Inject constructor(
    private val orderRepository: OrderRepository,
    private val hospitalRepository: HospitalRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(OrderUiState())
    val uiState: StateFlow<OrderUiState> = _uiState.asStateFlow()

    // MARK: - 列表

    /** 加载订单列表（status=null 为全部；按 token 身份区分患者/陪诊师视角）。 */
    fun loadOrders(status: String? = null) {
        _uiState.update { it.copy(isLoadingList = true, listError = false) }
        viewModelScope.launch {
            try {
                val orders = orderRepository.listOrders(status = status)
                _uiState.update { it.copy(isLoadingList = false, orders = orders, listFilter = status) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingList = false, listError = true) }
            }
        }
    }

    // MARK: - 详情

    fun loadOrderDetail(orderId: String) {
        _uiState.update { it.copy(isLoadingDetail = true, detailError = false) }
        viewModelScope.launch {
            try {
                val order = orderRepository.getOrder(orderId)
                _uiState.update { it.copy(isLoadingDetail = false, selectedOrder = order) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingDetail = false, detailError = true) }
            }
        }
    }

    fun cancelOrder(orderId: String) {
        if (_uiState.value.isMutating) return
        _uiState.update { it.copy(isMutating = true) }
        viewModelScope.launch {
            try {
                val order = orderRepository.cancelOrder(orderId)
                _uiState.update { it.copy(isMutating = false, selectedOrder = order) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, actionError = OrderErrorKey.CANCEL_FAILED) }
            }
        }
    }

    // MARK: - 支付

    /** 发起支付：mock 成功 → 复查订单 → 弹 pay-result。 */
    fun payOrder(orderId: String) {
        if (_uiState.value.isPaying) return
        _uiState.update { it.copy(isPaying = true, payResult = null) }
        viewModelScope.launch {
            try {
                val result = orderRepository.payOrder(orderId)
                _uiState.update {
                    it.copy(
                        isPaying = false,
                        payResult = if (result.success) PayOutcomeUi.SUCCESS else PayOutcomeUi.FAILED,
                        selectedOrder = result.order ?: it.selectedOrder,
                    )
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isPaying = false, payResult = PayOutcomeUi.FAILED) }
            }
        }
    }

    /** 关闭 pay-result 弹层。 */
    fun dismissPayResult() {
        _uiState.update { it.copy(payResult = null) }
    }

    // MARK: - 下单

    fun searchHospitals(keyword: String) {
        viewModelScope.launch {
            try {
                val list = hospitalRepository.searchHospitals(keyword)
                _uiState.update { it.copy(hospitals = list) }
            } catch (e: Exception) {
                _uiState.update { it.copy(hospitals = emptyList()) }
            }
        }
    }

    fun onSelectHospital(hospital: Hospital) {
        _uiState.update { it.copy(draft = it.draft.copy(hospital = hospital)) }
    }

    fun onServiceTypeChange(type: ServiceType) {
        _uiState.update { it.copy(draft = it.draft.copy(serviceType = type)) }
    }

    fun onDateChange(date: String) {
        _uiState.update { it.copy(draft = it.draft.copy(appointmentDate = date)) }
    }

    fun onTimeChange(time: String) {
        _uiState.update { it.copy(draft = it.draft.copy(appointmentTime = time)) }
    }

    fun onDescriptionChange(desc: String) {
        _uiState.update { it.copy(draft = it.draft.copy(description = desc)) }
    }

    /** 下单必填校验：医院 + 日期 + 时间。 */
    val canSubmitOrder: Boolean
        get() = _uiState.value.draft.let {
            it.hospital != null && it.appointmentDate.isNotBlank() && it.appointmentTime.isNotBlank()
        }

    /** 提交下单：成功后回调 onCreated（携带新订单 id 供跳详情）。 */
    fun submitOrder(onCreated: (Order) -> Unit) {
        val draft = _uiState.value.draft
        val hospital = draft.hospital ?: run {
            _uiState.update { it.copy(actionError = OrderErrorKey.HOSPITAL_REQUIRED) }
            return
        }
        if (_uiState.value.isSubmitting) return
        _uiState.update { it.copy(isSubmitting = true, actionError = null) }
        viewModelScope.launch {
            try {
                val order = orderRepository.createOrder(
                    CreateOrderRequest(
                        serviceType = draft.serviceType.value,
                        hospitalId = hospital.id,
                        appointmentDate = draft.appointmentDate,
                        appointmentTime = draft.appointmentTime,
                        description = draft.description.takeIf { it.isNotBlank() },
                    ),
                )
                _uiState.update { it.copy(isSubmitting = false, draft = OrderDraft()) }
                onCreated(order)
            } catch (e: Exception) {
                _uiState.update { it.copy(isSubmitting = false, actionError = OrderErrorKey.CREATE_FAILED) }
            }
        }
    }
}

/** 下单草稿。 */
data class OrderDraft(
    val hospital: Hospital? = null,
    val serviceType: ServiceType = ServiceType.FULL_ACCOMPANY,
    val appointmentDate: String = "",
    val appointmentTime: String = "",
    val description: String = "",
)

/** 支付结果 UI。 */
enum class PayOutcomeUi { SUCCESS, FAILED }

/** 订单操作错误 key（映射 i18n）。 */
enum class OrderErrorKey { CREATE_FAILED, CANCEL_FAILED, HOSPITAL_REQUIRED }

/** 订单 UI 状态（单一不可变快照）。 */
data class OrderUiState(
    // 列表
    val orders: List<Order> = emptyList(),
    val isLoadingList: Boolean = false,
    val listError: Boolean = false,
    val listFilter: String? = null,
    // 详情
    val selectedOrder: Order? = null,
    val isLoadingDetail: Boolean = false,
    val detailError: Boolean = false,
    // 支付
    val isPaying: Boolean = false,
    val payResult: PayOutcomeUi? = null,
    // 下单
    val draft: OrderDraft = OrderDraft(),
    val hospitals: List<Hospital> = emptyList(),
    val isSubmitting: Boolean = false,
    // 通用
    val isMutating: Boolean = false,
    val actionError: OrderErrorKey? = null,
)
