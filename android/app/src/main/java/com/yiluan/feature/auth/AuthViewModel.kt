package com.yiluan.feature.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.auth.AuthRepository
import com.yiluan.core.model.User
import com.yiluan.core.model.UserRole
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * 认证流程 ViewModel：手机 OTP 登录 + 首次选角色。
 * ANDROID-DEV-B1-AUTH — 对齐 iOS AuthViewModel 交互序列。
 *
 * 阶段（AuthStage）：
 *  PHONE_INPUT → OTP_INPUT → (登录成功) → 路由决策(role==null → ROLE_SELECT / 否则 DONE)
 */
@HiltViewModel
class AuthViewModel @Inject constructor(
    private val repository: AuthRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(AuthUiState())
    val uiState: StateFlow<AuthUiState> = _uiState.asStateFlow()

    // MARK: - 手机号 & OTP 输入

    fun onPhoneChange(phone: String) {
        _uiState.update { it.copy(phone = phone.filter(Char::isDigit).take(11), errorMessage = null) }
    }

    fun onCodeChange(code: String) {
        _uiState.update { it.copy(code = code.filter(Char::isDigit).take(6), errorMessage = null) }
    }

    /** 手机号是否合法（^1[3-9]\d{9}$，对齐后端校验）。 */
    val isPhoneValid: Boolean
        get() = PHONE_REGEX.matches(_uiState.value.phone)

    val isCodeValid: Boolean
        get() = CODE_REGEX.matches(_uiState.value.code)

    /** 发送验证码：成功进入 OTP 输入阶段。 */
    fun sendOtp() {
        val phone = _uiState.value.phone
        if (!PHONE_REGEX.matches(phone)) {
            _uiState.update { it.copy(errorMessage = ErrorKey.INVALID_PHONE) }
            return
        }
        if (_uiState.value.isSending) return
        _uiState.update { it.copy(isSending = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                repository.sendOtp(phone)
                _uiState.update {
                    it.copy(isSending = false, stage = AuthStage.OTP_INPUT, code = "")
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isSending = false, errorMessage = ErrorKey.SEND_OTP_FAILED) }
            }
        }
    }

    /** 验证 OTP 登录：成功后按 role 决定下一阶段。 */
    fun verifyOtp() {
        val state = _uiState.value
        if (!CODE_REGEX.matches(state.code)) {
            _uiState.update { it.copy(errorMessage = ErrorKey.INVALID_CODE) }
            return
        }
        if (state.isVerifying) return
        _uiState.update { it.copy(isVerifying = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                val user = repository.verifyOtp(state.phone, state.code)
                routeAfterLogin(user)
            } catch (e: Exception) {
                _uiState.update { it.copy(isVerifying = false, errorMessage = ErrorKey.VERIFY_OTP_FAILED) }
            }
        }
    }

    /** 回到手机号输入阶段（OTP 页返回）。 */
    fun backToPhoneInput() {
        _uiState.update { it.copy(stage = AuthStage.PHONE_INPUT, code = "", errorMessage = null) }
    }

    // MARK: - 选角色

    /** 首次选角色（不换 token）：成功进入 DONE。 */
    fun selectRole(role: UserRole) {
        if (_uiState.value.isSubmittingRole) return
        _uiState.update { it.copy(isSubmittingRole = true, errorMessage = null) }
        viewModelScope.launch {
            try {
                val user = repository.setRole(role.value)
                _uiState.update {
                    it.copy(isSubmittingRole = false, user = user, stage = AuthStage.DONE)
                }
            } catch (e: Exception) {
                _uiState.update { it.copy(isSubmittingRole = false, errorMessage = ErrorKey.SET_ROLE_FAILED) }
            }
        }
    }

    // MARK: - 路由决策

    /**
     * 登录后路由（对齐 iOS YiLuAnApp）：
     *  role==null → ROLE_SELECT；否则 → DONE（上层按 role 跳患者/陪诊员）。
     */
    private fun routeAfterLogin(user: User) {
        val stage = if (UserRole.fromValue(user.role) == null) {
            AuthStage.ROLE_SELECT
        } else {
            AuthStage.DONE
        }
        _uiState.update {
            it.copy(isVerifying = false, user = user, stage = stage)
        }
    }

    private companion object {
        val PHONE_REGEX = Regex("^1[3-9]\\d{9}$")
        val CODE_REGEX = Regex("^\\d{6}$")
    }
}

/** 认证阶段。 */
enum class AuthStage { PHONE_INPUT, OTP_INPUT, ROLE_SELECT, DONE }

/** 错误 key（映射到 i18n string，不在 ViewModel 里拼中文）。 */
enum class ErrorKey {
    INVALID_PHONE, INVALID_CODE, SEND_OTP_FAILED, VERIFY_OTP_FAILED, SET_ROLE_FAILED
}

/** 认证 UI 状态（单一不可变快照）。 */
data class AuthUiState(
    val stage: AuthStage = AuthStage.PHONE_INPUT,
    val phone: String = "",
    val code: String = "",
    val isSending: Boolean = false,
    val isVerifying: Boolean = false,
    val isSubmittingRole: Boolean = false,
    val user: User? = null,
    val errorMessage: ErrorKey? = null,
)
