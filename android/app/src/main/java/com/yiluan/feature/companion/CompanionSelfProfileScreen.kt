package com.yiluan.feature.companion

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R
import com.yiluan.core.model.CompanionProfile
import com.yiluan.core.model.CompanionStats

/**
 * 陪诊员本人资料页。
 * ANDROID-DEV-GAP-COMPANION-PROFILE — 替换原 COMPANION_PROFILE 路由复用 CompanionSetupScreen 的占位。
 * 对齐 iOS CompanionSelfProfileView + 小程序 companion/profile：
 * 实名 + 认证状态 + 统计卡(评分/总订单/总收入) + 简介 + 服务区域 + 编辑入口。
 * 数据层 loadMyProfile() 已有(B3)，本页只做 UI。
 */
@Composable
fun CompanionSelfProfileScreen(
    onEdit: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CompanionViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.loadMyProfile()
    }

    val profile = state.myProfile
    val stats = state.myStats

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(
            text = stringResource(R.string.companion_profile_title),
            style = MaterialTheme.typography.titleLarge,
        )

        if (profile == null && stats == null) {
            Text(text = stringResource(R.string.companion_profile_empty))
        } else {
            // Header: 实名 + 认证状态
            profile?.let { p ->
                Text(
                    text = p.realName ?: p.pseudonymName.orEmpty(),
                    style = MaterialTheme.typography.headlineSmall,
                )
                if (p.verificationStatus == "verified") {
                    Text(
                        text = stringResource(R.string.companion_verified),
                        style = MaterialTheme.typography.bodyMedium,
                    )
                }
            }

            // 统计卡: 评分 / 总订单 / 总收入
            StatsCard(profile = profile, stats = stats)

            // 简介
            profile?.bio?.takeIf { it.isNotBlank() }?.let { bio ->
                Text(
                    text = stringResource(R.string.companion_profile_bio),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(text = bio)
            }

            // 服务区域
            profile?.serviceArea?.takeIf { it.isNotBlank() }?.let { area ->
                Text(
                    text = stringResource(R.string.companion_profile_service_area),
                    style = MaterialTheme.typography.titleMedium,
                )
                Text(text = area)
            }
        }

        OutlinedButton(onClick = onEdit, modifier = Modifier.fillMaxWidth()) {
            Text(stringResource(R.string.companion_profile_edit))
        }
    }
}

@Composable
private fun StatsCard(
    profile: CompanionProfile?,
    stats: CompanionStats?,
    modifier: Modifier = Modifier,
) {
    // avgRating/totalOrders 优先取 stats，fallback profile；totalEarnings 仅 stats 有。
    val rating = stats?.avgRating ?: profile?.avgRating ?: 0.0
    val orders = stats?.totalOrders ?: profile?.totalOrders ?: 0
    val income = stats?.totalEarnings ?: "0.00"

    Card(modifier = modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            horizontalArrangement = Arrangement.SpaceEvenly,
        ) {
            StatItem(
                value = String.format("%.1f", rating),
                label = stringResource(R.string.companion_profile_stat_rating),
            )
            StatItem(
                value = orders.toString(),
                label = stringResource(R.string.companion_profile_stat_orders),
            )
            StatItem(
                value = stringResource(R.string.companion_profile_income_fmt, income),
                label = stringResource(R.string.companion_profile_stat_income),
            )
        }
    }
}

@Composable
private fun StatItem(
    value: String,
    label: String,
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.spacedBy(4.dp),
    ) {
        Text(text = value, style = MaterialTheme.typography.titleLarge)
        Text(
            text = label,
            style = MaterialTheme.typography.bodySmall,
            textAlign = TextAlign.Center,
        )
    }
}
