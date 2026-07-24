package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
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
 * 个人中心聚合页（枢纽）。
 * ANDROID-DEV-GAP-PROFILE-HUB-REACHABILITY — 对齐 iOS ProfileView + 小程序 profile/index。
 * 聚合下游子页入口（钱包/家人/紧急联系人/绑手机/复诊/通知/设置/关于 + 陪诊员主页），
 * 解决"子页注册了 composable 但无导航入口 = 死代码"的可达性缺口。
 */
@Composable
fun ProfileScreen(
    onEditProfile: () -> Unit,
    onBindPhone: () -> Unit,
    onWallet: () -> Unit,
    onFamily: () -> Unit,
    onEmergency: () -> Unit,
    onFollowups: () -> Unit,
    onNotifications: () -> Unit,
    onSettings: () -> Unit,
    onAbout: () -> Unit,
    onCompanionHome: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.loadProfile()
    }

    val isCompanion = state.profile?.roles?.contains("companion") == true

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = stringResource(R.string.profile_hub_title),
            style = MaterialTheme.typography.titleLarge,
        )

        MenuButton(text = stringResource(R.string.profile_hub_edit), onClick = onEditProfile)
        if (isCompanion) {
            MenuButton(text = stringResource(R.string.profile_hub_companion), onClick = onCompanionHome)
        }
        MenuButton(text = stringResource(R.string.profile_hub_bind_phone), onClick = onBindPhone)
        MenuButton(text = stringResource(R.string.profile_hub_wallet), onClick = onWallet)
        MenuButton(text = stringResource(R.string.profile_hub_family), onClick = onFamily)
        MenuButton(text = stringResource(R.string.profile_hub_emergency), onClick = onEmergency)
        MenuButton(text = stringResource(R.string.profile_hub_followup), onClick = onFollowups)
        MenuButton(text = stringResource(R.string.profile_hub_notifications), onClick = onNotifications)
        MenuButton(text = stringResource(R.string.profile_hub_settings), onClick = onSettings)
        MenuButton(text = stringResource(R.string.profile_hub_about), onClick = onAbout)
    }
}

@Composable
private fun MenuButton(
    text: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    OutlinedButton(onClick = onClick, modifier = modifier.fillMaxWidth()) {
        Text(text)
    }
}
