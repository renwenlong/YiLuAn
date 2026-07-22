package com.yiluan.feature.order

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Button
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.yiluan.R

/**
 * 支付结果页：成功/失败结果态 + 引导按钮。
 * ANDROID-DEV-GAP-PAY-RESULT — 补漏页，对齐小程序 patient/pay-result + iOS PaymentResultView。
 * 独立页承载支付后完整引导（弹层仅告知结果，缺 viewOrder/goHome/retry）：
 *  - 成功: viewOrder(看订单) / goHome(回首页)
 *  - 失败: retry(重试支付) / viewOrder(看订单)
 */
@Composable
fun PaymentResultScreen(
    isSuccess: Boolean,
    onViewOrder: () -> Unit,
    onGoHome: () -> Unit,
    onRetry: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Text(
            text = stringResource(
                if (isSuccess) R.string.pay_result_success_title
                else R.string.pay_result_fail_title,
            ),
        )
        Text(
            text = stringResource(
                if (isSuccess) R.string.pay_result_success_msg
                else R.string.pay_result_fail_msg,
            ),
        )

        if (isSuccess) {
            Button(onClick = onViewOrder, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.pay_result_view_order))
            }
            OutlinedButton(onClick = onGoHome, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.pay_result_go_home))
            }
        } else {
            Button(onClick = onRetry, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.pay_result_retry))
            }
            OutlinedButton(onClick = onViewOrder, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.pay_result_view_order))
            }
        }
    }
}
