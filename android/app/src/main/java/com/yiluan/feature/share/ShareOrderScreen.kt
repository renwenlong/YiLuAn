package com.yiluan.feature.share

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.yiluan.R
import com.yiluan.core.model.ShareTimelineItem

/**
 * Share 接收端脱敏订单内容（访客视角，无患者电话/身份证/病情）。
 * ANDROID-DEV-B5-PRECHECK-SHARE — 对齐 iOS ShareOrderView。由 ShareOtpScreen 成功后展示。
 */
@Composable
fun ShareOrderContent(state: ShareUiState, modifier: Modifier = Modifier) {
    val order = state.sharedOrder
    if (order == null) {
        Column(
            modifier = modifier.fillMaxSize().padding(24.dp),
            verticalArrangement = Arrangement.Center,
        ) { CircularProgressIndicator() }
        return
    }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = stringResource(R.string.share_order_title))
        order.hospitalName?.let { Text(text = stringResource(R.string.share_order_hospital_fmt, it)) }
        order.appointmentDate?.let { d ->
            Text(text = stringResource(R.string.order_appointment_fmt, d, order.appointmentTime ?: ""))
        }
        order.status?.let { Text(text = stringResource(R.string.share_order_status_fmt, it)) }
        order.patientNameMasked?.let { Text(text = stringResource(R.string.share_order_patient_fmt, it)) }
        order.companion?.name?.let { Text(text = stringResource(R.string.share_order_companion_fmt, it)) }

        // 时间线
        if (order.timeline.isNotEmpty()) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(text = stringResource(R.string.share_order_timeline_title))
                    order.timeline.forEach { TimelineRow(it) }
                }
            }
        }
    }
}

@Composable
private fun TimelineRow(item: ShareTimelineItem) {
    Text(
        text = buildString {
            item.at?.let { append(it); append("  ") }
            item.event?.let { append(it) }
            item.detail?.let { append(" · "); append(it) }
        },
    )
}
