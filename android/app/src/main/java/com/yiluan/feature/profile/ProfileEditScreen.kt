package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
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
 * 编辑资料页：回显当前昵称/头像 → 编辑 → 保存调 updateMe → 刷新。
 * ANDROID-DEV-GAP-PROFILE-EDIT — 补漏页，对齐小程序 profile/edit + iOS PatientProfileEditView。
 * 保存成功回调返回上一页(枢纽刷新资料)。
 */
@Composable
fun ProfileEditScreen(
    onSaved: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    var displayName by remember { mutableStateOf("") }
    var avatarUrl by remember { mutableStateOf("") }
    var initialized by remember { mutableStateOf(false) }

    LaunchedEffect(Unit) { viewModel.loadProfile() }

    // 资料拉到后回显一次（不覆盖用户正在编辑的输入）
    LaunchedEffect(state.profile) {
        if (!initialized && state.profile != null) {
            displayName = state.profile?.displayName.orEmpty()
            avatarUrl = state.profile?.avatarUrl.orEmpty()
            initialized = true
        }
    }

    // 保存成功 → 回调返回
    LaunchedEffect(state.profileSaved) {
        if (state.profileSaved) onSaved()
    }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = stringResource(R.string.profile_edit_title))

        OutlinedTextField(
            value = displayName,
            onValueChange = { displayName = it },
            label = { Text(stringResource(R.string.profile_edit_display_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = avatarUrl,
            onValueChange = { avatarUrl = it },
            label = { Text(stringResource(R.string.profile_edit_avatar_url)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Button(
            onClick = { viewModel.saveProfile(displayName, avatarUrl) },
            enabled = !state.isMutating && displayName.isNotBlank(),
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.profile_edit_save))
        }
    }
}
