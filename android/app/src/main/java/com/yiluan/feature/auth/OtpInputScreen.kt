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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import com.yiluan.R

/**
 * OTP 验证码输入屏（登录第二阶段）。
 * ANDROID-DEV-B1-AUTH — 对齐 iOS OTPInputView。
 */
@Composable
fun OtpInputScreen(
    state: AuthUiState,
    isCodeValid: Boolean,
    onCodeChange: (String) -> Unit,
    onVerify: () -> Unit,
    onBack: () -> Unit,
    errorText: String?,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.auth_otp_title))
        Text(text = stringResource(R.string.auth_otp_sent_to, state.phone))

        OutlinedTextField(
            value = state.code,
            onValueChange = onCodeChange,
            label = { Text(stringResource(R.string.auth_code_label)) },
            placeholder = { Text(stringResource(R.string.auth_code_placeholder)) },
            singleLine = true,
            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.NumberPassword),
            isError = errorText != null,
            modifier = Modifier.fillMaxWidth(),
        )

        if (errorText != null) {
            Text(text = errorText)
        }

        Button(
            onClick = onVerify,
            enabled = isCodeValid && !state.isVerifying,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isVerifying) {
                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            }
            Text(
                text = stringResource(
                    if (state.isVerifying) R.string.auth_verifying else R.string.auth_login,
                ),
            )
        }

        TextButton(
            onClick = onBack,
            enabled = !state.isVerifying,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(text = stringResource(R.string.auth_change_phone))
        }
    }
}
