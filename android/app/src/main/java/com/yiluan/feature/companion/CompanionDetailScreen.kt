package com.yiluan.feature.companion

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
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
import com.yiluan.core.model.CompanionProfile

/**
 * 陪诊员详情（患者视角，ABAC 脱敏）。
 * ANDROID-DEV-B3-COMPANION — 对齐 iOS CompanionDetailView。
 * 展示化名/评分/服务/认证，不含 real_name/id_number。
 */
@Composable
fun CompanionDetailScreen(
    companionId: String,
    modifier: Modifier = Modifier,
    viewModel: CompanionViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    LaunchedEffect(companionId) { viewModel.loadCompanionDetail(companionId) }

    when {
        state.isLoadingDetail -> Center { CircularProgressIndicator() }
        state.detailError -> Center { Text(stringResource(R.string.companion_detail_error)) }
        state.viewedCompanion != null ->
            CompanionDetailContent(profile = state.viewedCompanion!!, modifier = modifier)
    }
}

@Composable
private fun CompanionDetailContent(profile: CompanionProfile, modifier: Modifier = Modifier) {
    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = profile.displayName)
        if (profile.isVerified) {
            Text(text = stringResource(R.string.companion_verified))
        }
        Text(text = stringResource(R.string.companion_rating_fmt, profile.avgRating, profile.totalOrders))
        profile.serviceArea?.takeIf { it.isNotBlank() }?.let {
            Text(text = stringResource(R.string.companion_area_fmt, it))
        }
        if (profile.serviceTypeList.isNotEmpty()) {
            Text(text = stringResource(R.string.companion_types_fmt, profile.serviceTypeList.joinToString("、")))
        }
        profile.certificationType?.takeIf { it.isNotBlank() }?.let {
            Text(text = stringResource(R.string.companion_cert_fmt, it))
        }
        profile.bio?.takeIf { it.isNotBlank() }?.let {
            Text(text = stringResource(R.string.companion_bio_fmt, it))
        }

        // 维度评分
        profile.dimensionScores?.let { d ->
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(
                    modifier = Modifier.fillMaxWidth().padding(16.dp),
                    verticalArrangement = Arrangement.spacedBy(4.dp),
                ) {
                    Text(text = stringResource(R.string.companion_dimension_title))
                    d.punctuality?.let { Text(stringResource(R.string.companion_dim_punctuality, it)) }
                    d.professionalism?.let { Text(stringResource(R.string.companion_dim_professionalism, it)) }
                    d.communication?.let { Text(stringResource(R.string.companion_dim_communication, it)) }
                    d.attitude?.let { Text(stringResource(R.string.companion_dim_attitude, it)) }
                }
            }
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
