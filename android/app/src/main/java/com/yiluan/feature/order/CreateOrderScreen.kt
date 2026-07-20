package com.yiluan.feature.order

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.Card
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
import com.yiluan.core.model.Order
import com.yiluan.core.model.ServiceType

/**
 * 创建订单屏：选医院 + 服务类型 + 日期时间 + 描述。
 * ANDROID-DEV-B2-PATIENT — 对齐 iOS CreateOrderView。
 * 下单成功回调 onCreated（携新订单，上层跳详情）。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CreateOrderScreen(
    onCreated: (Order) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: OrderViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    val draft = state.draft

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.order_create_title))

        // 医院搜索
        OutlinedTextField(
            value = draft.hospital?.name ?: "",
            onValueChange = viewModel::searchHospitals,
            label = { Text(stringResource(R.string.order_hospital_label)) },
            placeholder = { Text(stringResource(R.string.order_hospital_placeholder)) },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        // 医院候选（短列表用 Column forEach，避免嵌套 LazyColumn 在 verticalScroll 中崩溃）
        if (state.hospitals.isNotEmpty() && draft.hospital == null) {
            Column(
                modifier = Modifier.fillMaxWidth(),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                state.hospitals.take(8).forEach { h ->
                    Card(
                        onClick = { viewModel.onSelectHospital(h) },
                        modifier = Modifier.fillMaxWidth(),
                    ) {
                        Text(text = h.name, modifier = Modifier.padding(12.dp))
                    }
                }
            }
        }

        // 服务类型
        Text(text = stringResource(R.string.order_service_type_label))
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            ServiceType.entries.forEach { type ->
                FilterChip(
                    selected = draft.serviceType == type,
                    onClick = { viewModel.onServiceTypeChange(type) },
                    label = { Text(stringResource(serviceTypeLabel(type))) },
                )
            }
        }

        // 日期时间（B2 用文本输入，日期选择器优化留后续）
        OutlinedTextField(
            value = draft.appointmentDate,
            onValueChange = viewModel::onDateChange,
            label = { Text(stringResource(R.string.order_date_label)) },
            placeholder = { Text("2026-08-01") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )
        OutlinedTextField(
            value = draft.appointmentTime,
            onValueChange = viewModel::onTimeChange,
            label = { Text(stringResource(R.string.order_time_label)) },
            placeholder = { Text("09:00") },
            singleLine = true,
            modifier = Modifier.fillMaxWidth(),
        )

        // 描述
        OutlinedTextField(
            value = draft.description,
            onValueChange = viewModel::onDescriptionChange,
            label = { Text(stringResource(R.string.order_desc_label)) },
            modifier = Modifier.fillMaxWidth(),
        )

        if (state.actionError == OrderErrorKey.HOSPITAL_REQUIRED) {
            Text(text = stringResource(R.string.order_err_hospital_required))
        }
        if (state.actionError == OrderErrorKey.CREATE_FAILED) {
            Text(text = stringResource(R.string.order_err_create_failed))
        }

        Button(
            onClick = { viewModel.submitOrder(onCreated) },
            enabled = viewModel.canSubmitOrder && !state.isSubmitting,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isSubmitting) {
                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            }
            Text(text = stringResource(R.string.order_submit))
        }
    }
}

@androidx.annotation.StringRes
private fun serviceTypeLabel(type: ServiceType): Int = when (type) {
    ServiceType.FULL_ACCOMPANY -> R.string.service_full_accompany
    ServiceType.HALF_ACCOMPANY -> R.string.service_half_accompany
    ServiceType.ERRAND -> R.string.service_errand
}
