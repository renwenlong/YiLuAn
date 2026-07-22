package com.yiluan.feature.share

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R
import com.yiluan.core.model.OrderShareToken
import com.yiluan.core.model.ShareScope

/**
 * Share 发起端管理屏（患者建分享 + 列表 + 撤销）。
 * ANDROID-DEV-B5-PRECHECK-SHARE — 对齐 iOS ShareManageView。上限 3，第 4 个自动撤最老。
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ShareManageScreen(
    orderId: String,
    modifier: Modifier = Modifier,
    viewModel: ShareViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()
    var scope by remember { mutableStateOf(ShareScope.PROGRESS_ONLY) }

    LaunchedEffect(orderId) { viewModel.loadShares(orderId) }

    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        Text(text = stringResource(R.string.share_manage_title))

        Row(
            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp),
            horizontalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            FilterChip(
                selected = scope == ShareScope.PROGRESS_ONLY,
                onClick = { scope = ShareScope.PROGRESS_ONLY },
                label = { Text(stringResource(R.string.share_scope_progress)) },
            )
            FilterChip(
                selected = scope == ShareScope.FULL,
                onClick = { scope = ShareScope.FULL },
                label = { Text(stringResource(R.string.share_scope_full)) },
            )
        }

        Button(
            onClick = { viewModel.createShare(orderId, scope.value) },
            enabled = !state.isMutating,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(stringResource(R.string.share_create))
        }

        if (state.error == ShareErrorKey.CREATE_FAILED) {
            Text(text = stringResource(R.string.share_err_create))
        }

        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(top = 12.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(state.shares, key = { it.id }) { token ->
                ShareRow(token, onRevoke = { viewModel.revokeShare(orderId, token.id) })
            }
        }
    }
}

@Composable
private fun ShareRow(token: OrderShareToken, onRevoke: () -> Unit) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.padding(end = 8.dp)) {
                Text(text = token.shareUrl)
                Text(
                    text = stringResource(
                        if (token.scope == ShareScope.FULL) R.string.share_scope_full
                        else R.string.share_scope_progress,
                    ),
                )
            }
            if (!token.isRevoked) {
                TextButton(onClick = onRevoke) {
                    Text(stringResource(R.string.share_revoke))
                }
            }
        }
    }
}
