package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
 * 设置屏：法务入口 + 注销账户（二次确认弹窗）。
 * ANDROID-DEV-B6-LONGTAIL — 对齐 iOS SettingsView + DeleteAccountView。
 * 注销永久不可恢复，后端不强制二次验证 → 前端必须二次确认。
 */
@Composable
fun SettingsScreen(
    onPrivacy: () -> Unit,
    onTerms: () -> Unit,
    onFollowups: () -> Unit,
    onEditProfile: () -> Unit,
    onAbout: () -> Unit,
    onAccountDeleted: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    var showDeleteConfirm by remember { mutableStateOf(false) }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = stringResource(R.string.settings_title))

        OutlinedButton(onClick = onEditProfile, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_edit_profile))
        }

        OutlinedButton(onClick = onPrivacy, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_privacy))
        }
        OutlinedButton(onClick = onTerms, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_terms))
        }

        OutlinedButton(onClick = onFollowups, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_followups))
        }

        OutlinedButton(onClick = onAbout, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.settings_about))
        }

        Button(
            onClick = { showDeleteConfirm = true },
            enabled = !state.isMutating,
            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error),
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isMutating) {
                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            }
            Text(stringResource(R.string.settings_delete_account))
        }
    }

    if (showDeleteConfirm) {
        AlertDialog(
            onDismissRequest = { showDeleteConfirm = false },
            title = { Text(stringResource(R.string.delete_account_confirm_title)) },
            text = { Text(stringResource(R.string.delete_account_confirm_msg)) },
            confirmButton = {
                TextButton(onClick = {
                    showDeleteConfirm = false
                    viewModel.deleteAccount(onAccountDeleted)
                }) {
                    Text(stringResource(R.string.delete_account_confirm_ok))
                }
            },
            dismissButton = {
                TextButton(onClick = { showDeleteConfirm = false }) {
                    Text(stringResource(R.string.common_cancel))
                }
            },
        )
    }
}
