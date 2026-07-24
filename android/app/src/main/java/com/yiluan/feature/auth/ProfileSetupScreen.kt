package com.yiluan.feature.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.yiluan.R

/**
 * 首次登录资料初始化引导页：填昵称 → updateMe(POST /users/me) → 进 home。
 * ANDROID-DEV-GAP-PROFILE-SETUP — 对齐 iOS ProfileSetupView + 小程序 profile/setup。
 * role 选完后若 displayName 空则路由到本页（AuthViewModel.resolveStage）。
 */
@Composable
fun ProfileSetupScreen(
    state: AuthUiState,
    onSubmit: (String) -> Unit,
    errorText: String?,
    modifier: Modifier = Modifier,
) {
    var displayName by remember { mutableStateOf("") }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(text = stringResource(R.string.profile_setup_title))
        Text(text = stringResource(R.string.profile_setup_subtitle))

        OutlinedTextField(
            value = displayName,
            onValueChange = { displayName = it },
            label = { Text(stringResource(R.string.profile_setup_nickname_hint)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        if (errorText != null) {
            Text(text = errorText)
        }

        Button(
            onClick = { onSubmit(displayName) },
            enabled = !state.isSubmittingProfile,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.profile_setup_finish))
        }
    }
}
