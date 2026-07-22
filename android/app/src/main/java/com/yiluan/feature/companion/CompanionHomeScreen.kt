package com.yiluan.feature.companion

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
 * 陪诊员首页：入口到抢单大厅/今日订单/入驻/我的档案。
 * ANDROID-DEV-B3-COMPANION — 对齐 iOS CompanionHomeView。
 */
@Composable
fun CompanionHomeScreen(
    onAvailableOrders: () -> Unit,
    onTodayOrders: () -> Unit,
    onSetup: () -> Unit,
    onProfile: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.companion_home_title))
        Text(text = stringResource(R.string.companion_home_subtitle))

        Button(onClick = onAvailableOrders, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.companion_home_available))
        }
        Button(onClick = onTodayOrders, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.companion_home_today))
        }
        OutlinedButton(onClick = onSetup, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.companion_home_setup))
        }
        OutlinedButton(onClick = onProfile, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.companion_home_profile))
        }
    }
}
