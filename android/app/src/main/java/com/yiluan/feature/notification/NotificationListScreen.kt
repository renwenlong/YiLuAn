package com.yiluan.feature.notification

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
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R
import com.yiluan.core.model.Notification

/**
 * 通知列表：WS 前台推 + REST 兜底 + 未读角标 + 标已读/全部已读。
 * ANDROID-DEV-B4-REALTIME — 对齐 iOS NotificationListView。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NotificationListScreen(
    modifier: Modifier = Modifier,
    viewModel: NotificationViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) { viewModel.enter() }

    Column(modifier = modifier.fillMaxSize()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(
                text = stringResource(R.string.notification_title_fmt, state.unreadCount),
            )
            if (state.unreadCount > 0) {
                TextButton(onClick = viewModel::markAllRead) {
                    Text(stringResource(R.string.notification_mark_all_read))
                }
            }
        }

        when {
            state.isLoading -> Column(modifier = Modifier.fillMaxSize().padding(24.dp)) { CircularProgressIndicator() }
            state.error -> Text(stringResource(R.string.notification_error), modifier = Modifier.padding(16.dp))
            state.notifications.isEmpty() -> Text(stringResource(R.string.notification_empty), modifier = Modifier.padding(16.dp))
            else -> LazyColumn(
                modifier = Modifier.fillMaxSize().padding(16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
            ) {
                items(state.notifications, key = { it.id }) { n ->
                    NotificationRow(n, onClick = { if (!n.isRead) viewModel.markRead(n.id) })
                }
            }
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun NotificationRow(n: Notification, onClick: () -> Unit) {
    Card(onClick = onClick, modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.fillMaxWidth().padding(16.dp)) {
            Text(text = n.title ?: stringResource(R.string.notification_untitled))
            n.body?.let { Text(text = it) }
            if (!n.isRead) {
                Text(text = stringResource(R.string.notification_unread_tag))
            }
        }
    }
}
