package com.yiluan.feature.auth

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.yiluan.R
import com.yiluan.core.model.UserRole

/**
 * 首次选角色屏（患者/陪诊员）。
 * ANDROID-DEV-B1-AUTH — 对齐 iOS RoleSelectionView。
 * 点卡片 → setRole(POST /users/me，不换 token) → 进主界面。
 */
@Composable
fun RoleSelectScreen(
    state: AuthUiState,
    onSelectRole: (UserRole) -> Unit,
    errorText: String?,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.auth_role_title))
        Text(text = stringResource(R.string.auth_role_subtitle))

        if (errorText != null) {
            Text(text = errorText)
        }

        RoleCard(
            title = stringResource(R.string.auth_role_patient),
            desc = stringResource(R.string.auth_role_patient_desc),
            enabled = !state.isSubmittingRole,
            onClick = { onSelectRole(UserRole.PATIENT) },
        )

        RoleCard(
            title = stringResource(R.string.auth_role_companion),
            desc = stringResource(R.string.auth_role_companion_desc),
            enabled = !state.isSubmittingRole,
            onClick = { onSelectRole(UserRole.COMPANION) },
        )

        if (state.isSubmittingRole) {
            CircularProgressIndicator()
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun RoleCard(
    title: String,
    desc: String,
    enabled: Boolean,
    onClick: () -> Unit,
) {
    Card(
        onClick = onClick,
        enabled = enabled,
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(text = title)
            Text(text = desc)
        }
    }
}
