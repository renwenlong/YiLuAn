package com.yiluan.feature.chat

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.weight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.OutlinedTextField
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
import com.yiluan.core.model.ChatMessage

/**
 * 聊天室：消息列表 + 输入发送（WS 实时，断线 backfill 补偿）。
 * ANDROID-DEV-B4-REALTIME — 对齐 iOS ChatRoomView。
 */
@Composable
fun ChatRoomScreen(
    orderId: String,
    modifier: Modifier = Modifier,
    viewModel: ChatViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(orderId) { viewModel.enter(orderId) }

    Column(modifier = modifier.fillMaxSize()) {
        if (!state.connected) {
            Text(
                text = stringResource(R.string.chat_reconnecting),
                modifier = Modifier.padding(8.dp),
            )
        }

        LazyColumn(
            modifier = Modifier.weight(1f).fillMaxWidth().padding(horizontal = 12.dp),
            verticalArrangement = Arrangement.spacedBy(6.dp),
        ) {
            items(state.messages, key = { it.id }) { msg ->
                MessageBubble(msg)
            }
        }

        Row(
            modifier = Modifier.fillMaxWidth().padding(8.dp),
            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
        ) {
            OutlinedTextField(
                value = state.input,
                onValueChange = viewModel::onInputChange,
                placeholder = { Text(stringResource(R.string.chat_input_hint)) },
                modifier = Modifier.weight(1f),
            )
            Button(
                onClick = viewModel::send,
                enabled = state.input.isNotBlank(),
                modifier = Modifier.padding(start = 8.dp),
            ) {
                Text(stringResource(R.string.chat_send))
            }
        }
    }
}

@Composable
private fun MessageBubble(msg: ChatMessage) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(12.dp)) {
            Text(text = msg.content)
            msg.createdAt?.let {
                Text(text = it)
            }
        }
    }
}
