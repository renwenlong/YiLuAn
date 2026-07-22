package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R
import com.yiluan.core.model.FollowupReminder

/**
 * 复诊提醒列表页：列表 + 空态 + 删除(仅 pending)。
 * ANDROID-DEV-GAP-FOLLOWUP-REMINDERS — 补漏页，对齐小程序 profile/followup-reminders + iOS FollowupRemindersView。
 * 数据来自 orders/me/followup-reminders(ProfileRepository.listFollowups)。
 */
@Composable
fun FollowupRemindersScreen(
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) { viewModel.loadFollowups() }

    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        Text(text = stringResource(R.string.followup_title))

        when {
            state.isLoadingFollowups -> {
                CircularProgressIndicator(modifier = Modifier.padding(top = 24.dp))
            }
            state.followups.isEmpty() -> {
                Text(
                    text = stringResource(R.string.followup_empty),
                    modifier = Modifier.padding(top = 24.dp),
                )
            }
            else -> {
                LazyColumn(
                    modifier = Modifier.fillMaxWidth().padding(top = 12.dp),
                    verticalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    items(state.followups, key = { it.id }) { reminder ->
                        FollowupReminderRow(
                            reminder = reminder,
                            onDelete = { viewModel.deleteFollowup(reminder.id) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun FollowupReminderRow(
    reminder: FollowupReminder,
    onDelete: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column {
                Text(text = reminder.remindAt)
                reminder.note?.takeIf { it.isNotBlank() }?.let {
                    Text(text = it)
                }
            }
            // 仅 pending 可删；其他状态不显示删除
            if (reminder.status == null || reminder.status == "pending") {
                TextButton(onClick = onDelete) {
                    Text(stringResource(R.string.followup_delete))
                }
            }
        }
    }
}
