package com.yiluan.feature.chat

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
import com.yiluan.feature.order.OrderViewModel

/**
 * 会话列表（复用 OrderViewModel 派生：进行中订单即会话）。
 * ANDROID-DEV-B4-REALTIME — 后端无独立 conversation, 由 Order 列表派生（一订单一会话）。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ChatListScreen(
    onConversationClick: (String) -> Unit,
    modifier: Modifier = Modifier,
    viewModel: OrderViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    // 会话 = accepted/in_progress/completed 订单（有陪诊关系可聊）。
    LaunchedEffect(Unit) { viewModel.loadOrders(status = null) }

    Column(modifier = modifier.fillMaxSize()) {
        Text(text = stringResource(R.string.chat_list_title), modifier = Modifier.padding(16.dp))
        when {
            state.isLoadingList -> Column(modifier = Modifier.fillMaxSize().padding(24.dp)) { CircularProgressIndicator() }
            else -> {
                val conversations = state.orders.filter {
                    it.status in setOf("accepted", "in_progress", "completed")
                }
                if (conversations.isEmpty()) {
                    Text(text = stringResource(R.string.chat_list_empty), modifier = Modifier.padding(16.dp))
                } else {
                    LazyColumn(
                        modifier = Modifier.fillMaxSize().padding(16.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        items(conversations, key = { it.id }) { order ->
                            ConversationRow(order, onClick = { onConversationClick(order.id) })
                        }
                    }
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun ConversationRow(order: Order, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(text = order.hospitalName ?: order.orderNumber)
            order.companionName?.let { Text(text = it) }
        }
    }
}
