package com.yiluan.feature.companion

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R
import com.yiluan.core.model.ServiceType

/**
 * 陪诊员入驻屏：真名 + 服务类型(多选) + 服务区域 + 身份证 + 简介。
 * ANDROID-DEV-B3-COMPANION — 对齐 iOS CompanionSetupView。提交后 pending 待审核。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CompanionSetupScreen(
    onApplied: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CompanionViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val draft = state.applyDraft

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.companion_setup_title))
        Text(text = stringResource(R.string.companion_setup_subtitle))

        OutlinedTextField(
            value = draft.realName,
            onValueChange = { v -> viewModel.onApplyFieldChange { it.copy(realName = v) } },
            label = { Text(stringResource(R.string.companion_real_name)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        Text(text = stringResource(R.string.companion_service_types))
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            ServiceType.entries.forEach { type ->
                val selected = type in draft.serviceTypes
                FilterChip(
                    selected = selected,
                    onClick = {
                        viewModel.onApplyFieldChange {
                            val next = if (selected) it.serviceTypes - type else it.serviceTypes + type
                            it.copy(serviceTypes = next)
                        }
                    },
                    label = { Text(stringResource(serviceTypeLabelCompanion(type))) },
                )
            }
        }

        OutlinedTextField(
            value = draft.serviceArea,
            onValueChange = { v -> viewModel.onApplyFieldChange { it.copy(serviceArea = v) } },
            label = { Text(stringResource(R.string.companion_service_area)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = draft.idNumber,
            onValueChange = { v -> viewModel.onApplyFieldChange { it.copy(idNumber = v) } },
            label = { Text(stringResource(R.string.companion_id_number)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = draft.bio,
            onValueChange = { v -> viewModel.onApplyFieldChange { it.copy(bio = v) } },
            label = { Text(stringResource(R.string.companion_bio)) },
            modifier = Modifier.fillMaxWidth(),
        )

        if (state.actionError == CompanionErrorKey.APPLY_INVALID) {
            Text(text = stringResource(R.string.companion_err_apply_invalid_msg))
        }
        if (state.actionError == CompanionErrorKey.APPLY_FAILED) {
            Text(text = stringResource(R.string.companion_err_apply_failed_msg))
        }

        Button(
            onClick = { viewModel.submitApply(onApplied) },
            enabled = viewModel.canSubmitApply && !state.isSubmittingApply,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isSubmittingApply) {
                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            }
            Text(stringResource(R.string.companion_setup_submit))
        }
    }
}

@androidx.annotation.StringRes
private fun serviceTypeLabelCompanion(type: ServiceType): Int = when (type) {
    ServiceType.FULL_ACCOMPANY -> R.string.service_full_accompany
    ServiceType.HALF_ACCOMPANY -> R.string.service_half_accompany
    ServiceType.ERRAND -> R.string.service_errand
}
