package com.yiluan.feature.precheck

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Card
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

/**
 * Precheck 4 信任卡 summary 屏（WS 推送刷新 + 轮询兜底）。
 * ANDROID-DEV-B5-PRECHECK-SHARE — 对齐 iOS OrderPrecheckSummaryView。
 */
@Composable
fun PrecheckSummaryScreen(
    orderId: String,
    modifier: Modifier = Modifier,
    viewModel: PrecheckViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(orderId) { viewModel.enter(orderId) }

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = stringResource(R.string.precheck_title))

        when {
            state.notFound -> Text(text = stringResource(R.string.precheck_not_found))
            state.loadError -> Text(text = stringResource(R.string.precheck_load_error))
            state.summary != null -> {
                val s = state.summary!!
                if (s.allReady) {
                    Text(text = stringResource(R.string.precheck_all_ready))
                }
                s.blockedReason?.let { Text(text = stringResource(R.string.precheck_blocked_fmt, it)) }

                // 合同卡
                s.contractStatus?.let { c ->
                    TrustCard(
                        title = stringResource(R.string.precheck_card_contract),
                        ready = c.ready,
                        detail = c.contractTemplateVersion?.let { v ->
                            stringResource(R.string.precheck_contract_version_fmt, v)
                        },
                    )
                }
                // 保险卡
                s.insuranceStatus?.let { i ->
                    TrustCard(
                        title = stringResource(R.string.precheck_card_insurance),
                        ready = i.ready,
                        detail = i.insurancePolicyNoMasked?.let { p ->
                            stringResource(R.string.precheck_insurance_policy_fmt, p)
                        },
                    )
                }
                // AI 准备包卡
                s.preparationStatus?.let { p ->
                    TrustCard(
                        title = stringResource(R.string.precheck_card_preparation),
                        ready = p.ready,
                        detail = p.sectionsCount?.let { n ->
                            stringResource(R.string.precheck_prep_sections_fmt, n)
                        },
                    )
                }
                // 陪诊师资质卡
                s.companionCertStatus?.let { cc ->
                    TrustCard(
                        title = stringResource(R.string.precheck_card_companion_cert),
                        ready = cc.ready,
                        detail = cc.pseudonymName?.let { name ->
                            stringResource(R.string.precheck_cert_name_fmt, name)
                        },
                    )
                }
            }
        }
    }
}

@Composable
private fun TrustCard(title: String, ready: Boolean, detail: String?) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(
            modifier = Modifier.fillMaxWidth().padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(4.dp),
        ) {
            Text(text = title)
            Text(
                text = stringResource(
                    if (ready) R.string.precheck_status_ready else R.string.precheck_status_pending,
                ),
            )
            detail?.let { Text(text = it) }
        }
    }
}
