package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R

/**
 * 绑定手机号：手机号 → 发码 → 输码 → 绑定。
 * ANDROID-DEV-B6-LONGTAIL — 对齐 iOS BindPhoneView。
 */
@Composable
fun BindPhoneScreen(
    onBound: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    var phone by remember { mutableStateOf("") }
    var code by remember { mutableStateOf("") }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.bind_phone_title))

        OutlinedTextField(
            value = phone,
            onValueChange = { phone = it.filter(Char::isDigit).take(11) },
            label = { Text(stringResource(R.string.auth_phone_label)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedButton(
            onClick = { viewModel.sendBindOtp(phone) },
            enabled = phone.length == 11 && !state.isMutating,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(if (state.bindOtpSent) R.string.bind_phone_resend else R.string.auth_send_otp))
        }

        OutlinedTextField(
            value = code,
            onValueChange = { code = it.filter(Char::isDigit).take(6) },
            label = { Text(stringResource(R.string.auth_code_label)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        if (state.error == ProfileErrorKey.BIND_FAILED) {
            Text(text = stringResource(R.string.bind_phone_failed))
        }
        if (state.error == ProfileErrorKey.INVALID_INPUT) {
            Text(text = stringResource(R.string.profile_err_invalid))
        }

        Button(
            onClick = { viewModel.bindPhone(phone, code, onBound) },
            enabled = phone.length == 11 && code.length == 6 && !state.isMutating,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isMutating) {
                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            }
            Text(stringResource(R.string.bind_phone_submit))
        }
    }
}
