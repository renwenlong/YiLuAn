package com.yiluan.feature.order

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R
import com.yiluan.core.model.Order

/**
 * 通用订单列表（患者/陪诊师角色态复用）。
 * ANDROID-DEV-B2-PATIENT — 对齐 iOS OrderListView（isCompanion 复用同一 View）。
 *
 * 列表数据不按角色分流（后端按 token 决定视角）；isCompanion 仅影响详情操作。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun OrderListScreen(
    isCompanion: Boolean,
    onOrderClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: OrderViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    var tabIndex by remember { mutableIntStateOf(0) }

    // Tab → status（对齐 iOS statusMap: 全部/待处理/进行中/已完成）。
    val tabs = remember {
        listOf<Pair<Int, String?>>(
            R.string.order_tab_all to null,
            R.string.order_tab_pending to "created",
            R.string.order_tab_in_progress to "in_progress",
            R.string.order_tab_completed to "completed",
        )
    }

    LaunchedEffect(tabIndex) {
        viewModel.loadOrders(status = tabs[tabIndex].second)
    }

    Column(modifier = modifier.fillMaxSize()) {
        ScrollableTabRow(selectedTabIndex = tabIndex) {
            tabs.forEachIndexed { i, (titleRes, _) ->
                Tab(
                    selected = tabIndex == i,
                    onClick = { tabIndex = i },
                    text = { Text(stringResource(titleRes)) },
                )
            }
        }

        when {
            state.isLoadingList -> CenterBox { CircularProgressIndicator() }
            state.listError -> CenterBox { Text(stringResource(R.string.order_list_error)) }
            state.orders.isEmpty() -> CenterBox { Text(stringResource(R.string.order_list_empty)) }
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(state.orders, key = { it.id }) { order ->
                    OrderRow(order = order, onClick = { onOrderClick(order.id) })
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun OrderRow(order: Order, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(text = order.hospitalName ?: order.orderNumber)
            Text(text = stringResource(orderStatusLabel(order.status)))
            Text(
                text = stringResource(R.string.order_appointment_fmt, order.appointmentDate, order.appointmentTime),
            )
            Text(text = stringResource(R.string.order_price_fmt, order.price))
        }
    }
}

@Composable
private fun CenterBox(content: @Composable () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.Center,
        horizontalAlignment = Alignment.CenterHorizontally,
    ) { content() }
}
