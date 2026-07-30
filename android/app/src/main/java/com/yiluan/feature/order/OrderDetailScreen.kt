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
import com.yiluan.core.model.Order
import com.yiluan.core.model.canCancel
import com.yiluan.core.model.canPay

/**
 * 订单详情屏：详情 + Precheck 信任卡占位 + 患者操作（支付/取消）+ pay-result。
 * ANDROID-DEV-B2-PATIENT — 对齐 iOS OrderDetailView。
 * Precheck 完整功能在 B5，此处仅占位信任卡。isCompanion 决定操作按钮集合。
 */
@Composable
fun OrderDetailScreen(
    orderId: String,
    isCompanion: Boolean,
    onNavigateToPayResult: (Boolean) -> Unit = {},
    onReview: () -> Unit = {},
    onShare: () -> Unit = {},
    modifier: Modifier = Modifier,
    viewModel: OrderViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(orderId) { viewModel.loadOrderDetail(orderId) }

    when {
        state.isLoadingDetail && state.selectedOrder == null ->
            CenterColumn { CircularProgressIndicator() }
        state.detailError ->
            CenterColumn { Text(stringResource(R.string.order_detail_error)) }
        state.selectedOrder != null ->
            OrderDetailContent(
                order = state.selectedOrder!!,
                isCompanion = isCompanion,
                isPaying = state.isPaying,
                isMutating = state.isMutating,
                onPay = { viewModel.payOrder(orderId) },
                onCancel = { viewModel.cancelOrder(orderId) },
                onReview = onReview,
                onShare = onShare,
                modifier = modifier,
            )
    }

    // 支付有结果 → 导航到独立支付结果页(带 viewOrder/goHome/retry 引导), 导航后清除避免重复触发
    LaunchedEffect(state.payResult) {
        state.payResult?.let { outcome ->
            onNavigateToPayResult(outcome == PayOutcomeUi.SUCCESS)
            viewModel.dismissPayResult()
        }
    }
}

@Composable
private fun OrderDetailContent(
    order: Order,
    isCompanion: Boolean,
    isPaying: Boolean,
    isMutating: Boolean,
    onPay: () -> Unit,
    onCancel: () -> Unit,
    onReview: () -> Unit = {},
    onShare: () -> Unit = {},
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = order.hospitalName ?: order.orderNumber)
        Text(text = stringResource(orderStatusLabel(order.status)))
        Text(text = stringResource(R.string.order_number_fmt, order.orderNumber))
        Text(text = stringResource(R.string.order_appointment_fmt, order.appointmentDate, order.appointmentTime))
        Text(text = stringResource(R.string.order_price_fmt, order.price))
        order.description?.takeIf { it.isNotBlank() }?.let {
            Text(text = stringResource(R.string.order_desc_fmt, it))
        }

        // Precheck 信任卡占位（完整功能 B5）
        PrecheckPlaceholderCard()

        // 患者操作（isCompanion=false 时显示支付/取消；陪诊师操作 B3 落地）
        if (!isCompanion) {
            if (order.canPay) {
                Button(
                    onClick = onPay,
                    enabled = !isPaying,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    if (isPaying) {
                        CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
                    }
                    Text(stringResource(R.string.order_pay_now))
                }
            }
            if (order.canCancel) {
                OutlinedButton(
                    onClick = onCancel,
                    enabled = !isMutating,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(stringResource(R.string.order_cancel))
                }
            }
            // 分享给家属入口（GAP-PROFILE-HUB 可达性）。
            OutlinedButton(
                onClick = onShare,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.share_manage_title))
            }
            // 写评价入口（完成态显示，GAP-PROFILE-HUB 可达性）。
            if (order.status == "completed") {
                OutlinedButton(
                    onClick = onReview,
                    modifier = Modifier.fillMaxWidth(),
                ) {
                    Text(stringResource(R.string.review_title))
                }
            }
        }
    }
}

/** Precheck 信任卡占位（B5 完整）。 */
@Composable
private fun PrecheckPlaceholderCard() {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(text = stringResource(R.string.precheck_title))
            Text(text = stringResource(R.string.precheck_placeholder))
        }
    }
}

@Composable
private fun CenterColumn(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
    ) { content() }
}
