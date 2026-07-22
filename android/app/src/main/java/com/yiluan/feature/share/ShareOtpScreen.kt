package com.yiluan.feature.share

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R

/**
 * Share 接收端 OTP 屏（访客：手机号 → 验证码 → 换 session → 脱敏订单）。
 * ANDROID-DEV-B5-PRECHECK-SHARE — 对齐 iOS ShareOTPView 状态机。
 */
@Composable
fun ShareOtpScreen(
    token: String,
    modifier: Modifier = Modifier,
    viewModel: ShareViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    // 已有有效 session 直接进订单视图。
    LaunchedEffect(token) { viewModel.loadShareOrder() }

    when (state.otpStage) {
        OtpStage.ENTER_PHONE -> PhoneStage(state, viewModel, token, modifier)
        OtpStage.ENTER_OTP -> OtpStage(state, viewModel, token, modifier)
        OtpStage.SUCCESS -> ShareOrderContent(state, modifier)
    }
}

@Composable
private fun PhoneStage(state: ShareUiState, vm: ShareViewModel, token: String, modifier: Modifier) {
    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.share_otp_title))
        Text(text = stringResource(R.string.share_otp_subtitle))
        OutlinedTextField(
            value = state.phone,
            onValueChange = vm::onPhoneChange,
            label = { Text(stringResource(R.string.auth_phone_label)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        if (state.error == ShareErrorKey.INVALID_PHONE) {
            Text(text = stringResource(R.string.auth_err_invalid_phone))
        }
        if (state.error == ShareErrorKey.SEND_OTP_FAILED) {
            Text(text = stringResource(R.string.auth_err_send_otp_failed))
        }
        Button(
            onClick = { vm.sendOtp(token) },
            enabled = state.phone.length == 11 && !state.isMutating,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isMutating) CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            Text(stringResource(R.string.auth_send_otp))
        }
    }
}

@Composable
private fun OtpStage(state: ShareUiState, vm: ShareViewModel, token: String, modifier: Modifier) {
    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.auth_otp_title))
        state.maskedPhone?.let { Text(text = stringResource(R.string.auth_otp_sent_to, it)) }
        OutlinedTextField(
            value = state.otp,
            onValueChange = vm::onOtpChange,
            label = { Text(stringResource(R.string.auth_code_label)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        if (state.error == ShareErrorKey.VERIFY_OTP_FAILED) {
            Text(text = stringResource(R.string.auth_err_verify_otp_failed))
        }
        Button(
            onClick = { vm.exchangeSession(token) },
            enabled = state.otp.length == 6 && !state.isMutating,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isMutating) CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            Text(stringResource(R.string.auth_login))
        }
        TextButton(onClick = vm::backToPhone, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.auth_change_phone))
        }
    }
}
