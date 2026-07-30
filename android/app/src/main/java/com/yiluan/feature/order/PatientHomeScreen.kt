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
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.yiluan.R

/**
 * 患者首页：下单 / 我的订单 / 陪诊员工作台(B3) / 设置(B6) / 消息+通知(B4)。
 * ANDROID-DEV-B2-PATIENT — 对齐 iOS PatientHomeView。
 */
@Composable
fun PatientHomeScreen(
    onCreateOrder: () -> Unit,
    onMyOrders: () -> Unit,
    onSettings: (() -> Unit)? = null,
    onCompanionMode: (() -> Unit)? = null,
    onChat: (() -> Unit)? = null,
    onNotifications: (() -> Unit)? = null,
    onProfile: (() -> Unit)? = null,
    onFindCompanion: (() -> Unit)? = null,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.patient_home_title))
        Text(text = stringResource(R.string.patient_home_subtitle))

        Button(
            onClick = onCreateOrder,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.patient_home_create_order))
        }

        OutlinedButton(
            onClick = onMyOrders,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.patient_home_my_orders))
        }

        // 陪诊员工作台入口（B3）。
        if (onCompanionMode != null) {
            OutlinedButton(
                onClick = onCompanionMode,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.patient_home_companion_mode))
            }
        }

        // 个人中心（我的）入口（GAP-PROFILE-HUB）——聚合钱包/家人/紧急/绑手机/复诊等入口。
        if (onProfile != null) {
            OutlinedButton(
                onClick = onProfile,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.profile_hub_title))
            }
        }

        // 找陪诊师入口（GAP-COMPANION-LIST-DETAIL 可达性）。
        if (onFindCompanion != null) {
            OutlinedButton(
                onClick = onFindCompanion,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.patient_home_find_companion))
            }
        }

        // 设置入口（B6）。
        if (onSettings != null) {
            OutlinedButton(
                onClick = onSettings,
                modifier = Modifier.fillMaxWidth(),
            ) {
                Text(stringResource(R.string.patient_home_settings))
            }
        }

        // 聊天/通知入口（B4）。
        if (onChat != null) {
            OutlinedButton(onClick = onChat, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.patient_home_chat))
            }
        }
        if (onNotifications != null) {
            OutlinedButton(onClick = onNotifications, modifier = Modifier.fillMaxWidth()) {
                Text(stringResource(R.string.patient_home_notifications))
            }
        }
    }
}
