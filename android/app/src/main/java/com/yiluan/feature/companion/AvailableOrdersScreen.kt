package com.yiluan.feature.companion

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R
import com.yiluan.core.model.Order
import com.yiluan.feature.order.orderStatusLabel

/**
 * 抢单大厅（陪诊员）：列出 created 单，行内接单 + 前置门槛错误引导。
 * ANDROID-DEV-B3-COMPANION — 对齐 iOS AvailableOrdersView。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AvailableOrdersScreen(
    onOrderClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CompanionViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) { viewModel.loadAvailableOrders() }

    Column(modifier = modifier.fillMaxSize()) {
        Text(
            text = stringResource(R.string.companion_available_title),
            modifier = Modifier.padding(16.dp),
        )
        when {
            state.isLoadingAvailable -> Center { CircularProgressIndicator() }
            state.availableError -> Center { Text(stringResource(R.string.companion_available_error)) }
            state.availableOrders.isEmpty() -> Center { Text(stringResource(R.string.companion_available_empty)) }
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(state.availableOrders, key = { it.id }) { order ->
                    AvailableOrderRow(
                        order = order,
                        accepting = state.actingOrderId == order.id,
                        onAccept = { viewModel.acceptOrder(order.id) },
                        onClick = { onOrderClick(order.id) },
                    )
                }
            }
        }
    }

    // 前置门槛 / 接单失败弹层
    state.actionError?.let { key ->
        val (titleRes, msgRes) = companionErrorText(key)
        AlertDialog(
            onDismissRequest = viewModel::clearActionError,
            confirmButton = {
                TextButton(onClick = viewModel::clearActionError) {
                    Text(stringResource(R.string.common_ok))
                }
            },
            title = { Text(stringResource(titleRes)) },
            text = { Text(stringResource(msgRes)) },
        )
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun AvailableOrderRow(
    order: Order,
    accepting: Boolean,
    onAccept: () -> Unit,
    onClick: () -> Unit,
) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            Text(text = order.hospitalName ?: order.orderNumber)
            Text(text = stringResource(orderStatusLabel(order.status)))
            Text(
                text = stringResource(
                    R.string.order_appointment_fmt,
                    order.appointmentDate,
                    order.appointmentTime,
                ),
            )
            Text(text = stringResource(R.string.order_price_fmt, order.price))
            Button(
                onClick = onAccept,
                enabled = !accepting,
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (accepting) {
                    CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
                }
                Text(stringResource(R.string.companion_accept))
            }
        }
    }
}

@Composable
private fun Center(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) { content() }
}

/** 陪诊员错误 key → (title res, message res)。 */
@Composable
internal fun companionErrorText(key: CompanionErrorKey): Pair<Int, Int> = when (key) {
    CompanionErrorKey.PHONE_REQUIRED ->
        R.string.companion_err_phone_title to R.string.companion_err_phone_msg
    CompanionErrorKey.VERIFICATION_REQUIRED ->
        R.string.companion_err_verify_title to R.string.companion_err_verify_msg
    CompanionErrorKey.ACCEPT_FAILED ->
        R.string.companion_err_action_title to R.string.companion_err_accept_msg
    CompanionErrorKey.ACTION_FAILED ->
        R.string.companion_err_action_title to R.string.companion_err_action_msg
    CompanionErrorKey.APPLY_INVALID ->
        R.string.companion_err_action_title to R.string.companion_err_apply_invalid_msg
    CompanionErrorKey.APPLY_FAILED ->
        R.string.companion_err_action_title to R.string.companion_err_apply_failed_msg
}
