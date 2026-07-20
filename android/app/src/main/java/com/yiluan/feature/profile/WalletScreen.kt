package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Card
import androidx.compose.material3.CircularProgressIndicator
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
import com.yiluan.core.model.PaymentTransaction

/**
 * 钱包：余额概览 + 交易流水。
 * ANDROID-DEV-B6-LONGTAIL — 对齐 iOS WalletView。
 */
@Composable
fun WalletScreen(
    modifier: Modifier = Modifier,
    viewModel: ProfileViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(Unit) { viewModel.loadWallet() }

    Column(modifier = modifier.fillMaxSize().padding(16.dp)) {
        Text(text = stringResource(R.string.wallet_title))

        if (state.isLoadingWallet) {
            CircularProgressIndicator()
        }

        state.wallet?.let { w ->
            Card(modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(text = stringResource(R.string.wallet_balance_fmt, w.balance))
                    Text(text = stringResource(R.string.wallet_income_fmt, w.totalIncome))
                    Text(text = stringResource(R.string.wallet_expense_fmt, w.totalExpense))
                    Text(text = stringResource(R.string.wallet_withdrawable_fmt, w.withdrawable))
                }
            }
        }

        Text(text = stringResource(R.string.wallet_transactions_title), modifier = Modifier.padding(top = 8.dp))
        LazyColumn(
            modifier = Modifier.fillMaxSize(),
            verticalArrangement = Arrangement.spacedBy(8.dp),
        ) {
            items(state.transactions, key = { it.id }) { t ->
                TransactionRow(t)
            }
        }
    }
}

@Composable
private fun TransactionRow(t: PaymentTransaction) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(12.dp),
            verticalArrangement = Arrangement.spacedBy(2.dp),
        ) {
            Text(text = stringResource(R.string.wallet_amount_fmt, t.amount))
            t.paymentType?.let { Text(text = it) }
            t.createdAt?.let { Text(text = it) }
        }
    }
}
