package com.yiluan.feature.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.yiluan.R

/**
 * 手机号输入屏（登录第一阶段）。
 * ANDROID-DEV-B1-AUTH — 对齐 iOS LoginView 手机 OTP 入口。
 */
@Composable
fun PhoneInputScreen(
    state: AuthUiState,
    isPhoneValid: Boolean,
    onPhoneChange: (String) -> Unit,
    onSendOtp: () -> Unit,
    errorText: String?,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.auth_login_title))
        Text(text = stringResource(R.string.auth_login_subtitle))

        OutlinedTextField(
            value = state.phone,
            onValueChange = onPhoneChange,
            label = { Text(stringResource(R.string.auth_phone_label)) },
            placeholder = { Text(stringResource(R.string.auth_phone_placeholder)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Phone),
            isError = errorText != null,
            modifier = Modifier.fillMaxWidth(),
        )

        if (errorText != null) {
            Text(text = errorText)
        }

        Button(
            onClick = onSendOtp,
            enabled = isPhoneValid && !state.isSending,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isSending) {
                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            }
            Text(
                text = stringResource(
                    if (state.isSending) R.string.auth_sending else R.string.auth_send_otp,
                ),
            )
        }
    }
}
