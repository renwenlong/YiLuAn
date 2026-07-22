package com.yiluan.feature.share

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.model.OrderShareToken
import com.yiluan.core.model.ShareOrderResponse
import com.yiluan.core.share.ShareRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * Share ViewModel：发起端管理(建/列表/撤销) + 接收端 OTP 状态机 + 脱敏订单。
 * ANDROID-DEV-B5-PRECHECK-SHARE — 对齐 iOS ShareManageViewModel + ShareOTPViewModel。
 */
@HiltViewModel
class ShareViewModel @Inject constructor(
    private val repository: ShareRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ShareUiState())
    val uiState: StateFlow<ShareUiState> = _uiState.asStateFlow()

    // ── 发起端管理 ──

    fun loadShares(orderId: String) {
        _uiState.update { it.copy(isLoadingShares = true) }
        viewModelScope.launch {
            try {
                val items = repository.listShares(orderId)
                _uiState.update { it.copy(isLoadingShares = false, shares = items) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingShares = false, error = ShareErrorKey.LOAD_FAILED) }
            }
        }
    }

    fun createShare(orderId: String, scope: String) {
        if (_uiState.value.isMutating) return
        _uiState.update { it.copy(isMutating = true, error = null) }
        viewModelScope.launch {
            try {
                repository.createShare(orderId, scope)
                _uiState.update { it.copy(isMutating = false) }
                loadShares(orderId)
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ShareErrorKey.CREATE_FAILED) }
            }
        }
    }

    fun revokeShare(orderId: String, tokenId: String) {
        viewModelScope.launch {
            try {
                repository.revokeShare(orderId, tokenId)
                loadShares(orderId)
            } catch (e: Exception) {
                _uiState.update { it.copy(error = ShareErrorKey.REVOKE_FAILED) }
            }
        }
    }

    // ── 接收端 OTP 状态机 ──

    fun onPhoneChange(v: String) = _uiState.update { it.copy(phone = v.filter(Char::isDigit).take(11), error = null) }
    fun onOtpChange(v: String) = _uiState.update { it.copy(otp = v.filter(Char::isDigit).take(6), error = null) }

    /** 发送 OTP（分享场景），成功进入输码阶段。 */
    fun sendOtp(token: String) {
        val phone = _uiState.value.phone
        if (!PHONE_REGEX.matches(phone)) {
            _uiState.update { it.copy(error = ShareErrorKey.INVALID_PHONE) }
            return
        }
        if (_uiState.value.isMutating) return
        _uiState.update { it.copy(isMutating = true, error = null) }
        viewModelScope.launch {
            try {
                val resp = repository.sendOtp(token, phone)
                _uiState.update {
                    it.copy(
                        isMutating = false,
                        otpStage = OtpStage.ENTER_OTP,
                        maskedPhone = resp.maskedPhone,
                        otpExpiresIn = resp.expiresIn,
                    )
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ShareErrorKey.SEND_OTP_FAILED) }
            }
        }
    }

    /** 验证 OTP 换 session，成功后拉脱敏订单。 */
    fun exchangeSession(token: String) {
        val s = _uiState.value
        if (!OTP_REGEX.matches(s.otp)) {
            _uiState.update { it.copy(error = ShareErrorKey.INVALID_OTP) }
            return
        }
        if (s.isMutating) return
        _uiState.update { it.copy(isMutating = true, error = null) }
        viewModelScope.launch {
            try {
                repository.exchangeSession(token, s.phone, s.otp)
                _uiState.update { it.copy(isMutating = false, otpStage = OtpStage.SUCCESS) }
                loadShareOrder()
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ShareErrorKey.VERIFY_OTP_FAILED) }
            }
        }
    }

    /** 拉脱敏订单（用本地 share_session）；null 仅表未加载到，不重置 stage。 */
    fun loadShareOrder() {
        viewModelScope.launch {
            try {
                val order = repository.shareOrder()
                if (order != null) {
                    _uiState.update { it.copy(sharedOrder = order) }
                }
                // order==null 时保持当前 stage（SUCCESS 后订单可能未拉到, 展示 loading），
                // 不打回 OTP；真正 session 过期走 catch(401) 分支。
            } catch (e: Exception) {
                // 401 → session 过期/被 revoke → 回 OTP
                repository.clearSession()
                _uiState.update { it.copy(otpStage = OtpStage.ENTER_PHONE, sharedOrder = null) }
            }
        }
    }

    fun backToPhone() = _uiState.update { it.copy(otpStage = OtpStage.ENTER_PHONE, otp = "", error = null) }

    fun clearError() = _uiState.update { it.copy(error = null) }

    private companion object {
        val PHONE_REGEX = Regex("^1[3-9]\\d{9}$")
        val OTP_REGEX = Regex("^\\d{6}$")
    }
}

enum class OtpStage { ENTER_PHONE, ENTER_OTP, SUCCESS }

enum class ShareErrorKey {
    LOAD_FAILED, CREATE_FAILED, REVOKE_FAILED,
    INVALID_PHONE, INVALID_OTP, SEND_OTP_FAILED, VERIFY_OTP_FAILED,
}

data class ShareUiState(
    // 发起端
    val shares: List<OrderShareToken> = emptyList(),
    val isLoadingShares: Boolean = false,
    val isMutating: Boolean = false,
    // 接收端 OTP
    val otpStage: OtpStage = OtpStage.ENTER_PHONE,
    val phone: String = "",
    val otp: String = "",
    val maskedPhone: String? = null,
    val otpExpiresIn: Int = 0,
    // 脱敏订单
    val sharedOrder: ShareOrderResponse? = null,
    val error: ShareErrorKey? = null,
)
