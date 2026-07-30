package com.yiluan.feature.companion

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
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
import com.yiluan.core.model.CompanionDirectoryItem

/**
 * 患者浏览陪诊师列表页。
 * ANDROID-DEV-GAP-COMPANION-LIST-DETAIL — 补 companion_detail 可达性(第8处缺口)。
 * 微信 golden 从 patient/home 陪诊师推荐进详情；安卓缺列表入口 → companion_detail 死代码。
 * 本页拉列表 → 卡片点击 navigate 到详情，使 companion_detail 可达。
 */
@Composable
fun CompanionListScreen(
    onCompanionClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CompanionViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) {
        viewModel.loadCompanions()
    }

    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = stringResource(R.string.companion_list_title),
            style = MaterialTheme.typography.titleLarge,
        )

        when {
            state.isLoadingCompanions && state.companions.isEmpty() ->
                CircularProgressIndicator()
            state.companionsError ->
                Text(text = stringResource(R.string.companion_list_error))
            state.companions.isEmpty() ->
                Text(text = stringResource(R.string.companion_list_empty))
            else ->
                LazyColumn(
                    modifier = Modifier.fillMaxWidth(),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.companions, key = { it.id }) { item ->
                        CompanionCard(item = item, onClick = { onCompanionClick(item.id) })
                    }
                }
        }
    }
}

@Composable
private fun CompanionCard(
    item: CompanionDirectoryItem,
    onClick: () -> Unit,
    modifier: Modifier = Modifier,
) {
    Card(
        modifier = modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(
                text = item.pseudonymName.orEmpty(),
                style = MaterialTheme.typography.titleMedium,
            )
            item.serviceArea?.takeIf { it.isNotBlank() }?.let {
                Text(text = it, style = MaterialTheme.typography.bodyMedium)
            }
            Text(
                text = stringResource(
                    R.string.companion_list_rating_fmt,
                    String.format("%.1f", item.avgRating),
                    item.totalOrders,
                ),
                style = MaterialTheme.typography.bodySmall,
            )
        }
    }
}
