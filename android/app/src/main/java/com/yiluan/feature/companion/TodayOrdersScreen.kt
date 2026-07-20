package com.yiluan.feature.companion

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
import com.yiluan.feature.order.orderStatusLabel
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * 今日订单（陪诊员）：accepted 单里筛今日 appointment_date。
 * ANDROID-DEV-B3-COMPANION — 对齐 iOS TodayOrdersView（客户端按今日过滤）。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TodayOrdersScreen(
    onOrderClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: CompanionViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    // 用 SimpleDateFormat 取今日 YYYY-MM-DD（minSdk24 无 desugaring, 不用 java.time.LocalDate）。
    val today = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())

    LaunchedEffect(today) { viewModel.loadTodayOrders(today) }

    Column(modifier = modifier.fillMaxSize()) {
        Text(
            text = stringResource(R.string.companion_today_title),
            modifier = Modifier.padding(16.dp),
        )
        when {
            state.isLoadingToday -> Center { CircularProgressIndicator() }
            state.todayError -> Center { Text(stringResource(R.string.companion_today_error)) }
            state.todayOrders.isEmpty() -> Center { Text(stringResource(R.string.companion_today_empty)) }
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(12.dp),
            ) {
                items(state.todayOrders, key = { it.id }) { order ->
                    TodayOrderRow(order = order, onClick = { onOrderClick(order.id) })
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun TodayOrderRow(order: Order, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
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
