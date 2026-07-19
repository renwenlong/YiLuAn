package com.yiluan.feature.auth

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R

/**
 * 认证流程容器：按 stage 分发到手机号/OTP/选角色屏，登录完成回调 onAuthenticated。
 * ANDROID-DEV-B1-AUTH — 对齐 iOS AuthView 的阶段切换 + 登录后路由决策。
 */
@Composable
fun AuthScreen(
    onAuthenticated: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: AuthViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val errorText = state.errorMessage?.let { stringResource(errorStringRes(it)) }

    when (state.stage) {
        AuthStage.PHONE_INPUT -> PhoneInputScreen(
            state = state,
            isPhoneValid = viewModel.isPhoneValid,
            onPhoneChange = viewModel::onPhoneChange,
            onSendOtp = viewModel::sendOtp,
            errorText = errorText,
            modifier = modifier,
        )

        AuthStage.OTP_INPUT -> OtpInputScreen(
            state = state,
            isCodeValid = viewModel.isCodeValid,
            onCodeChange = viewModel::onCodeChange,
            onVerify = viewModel::verifyOtp,
            onBack = viewModel::backToPhoneInput,
            errorText = errorText,
            modifier = modifier,
        )

        AuthStage.ROLE_SELECT -> RoleSelectScreen(
            state = state,
            onSelectRole = viewModel::selectRole,
            errorText = errorText,
            modifier = modifier,
        )

        AuthStage.DONE -> LaunchedEffect(Unit) { onAuthenticated() }
    }
}

/** ErrorKey → i18n string res（不在 ViewModel 拼中文，UI 层统一映射）。 */
private fun errorStringRes(key: ErrorKey): Int = when (key) {
    ErrorKey.INVALID_PHONE -> R.string.auth_err_invalid_phone
    ErrorKey.INVALID_CODE -> R.string.auth_err_invalid_code
    ErrorKey.SEND_OTP_FAILED -> R.string.auth_err_send_otp_failed
    ErrorKey.VERIFY_OTP_FAILED -> R.string.auth_err_verify_otp_failed
    ErrorKey.SET_ROLE_FAILED -> R.string.auth_err_set_role_failed
}
