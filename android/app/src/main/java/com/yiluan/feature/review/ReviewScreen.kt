package com.yiluan.feature.review

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.FilterChip
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.yiluan.R

/**
 * 写评价屏（患者对已完成订单，4 维度评分 + content）。
 * ANDROID-DEV-B6-LONGTAIL — ⚠️ 提交驱动订单 completed→reviewed（业务功能）。
 * 从「已完成订单」入口进入，提交成功后订单变 reviewed。
 */
@Composable
fun ReviewScreen(
    orderId: String,
    onSubmitted: () -> Unit,
    modifier: Modifier = Modifier,
    viewModel: ReviewViewModel = hiltViewModel(),
) {
    val state by viewModel.uiState.collectAsState()

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(16.dp),
    ) {
        Text(text = stringResource(R.string.review_title))

        RatingRow(stringResource(R.string.review_punctuality), state.punctuality, viewModel::setPunctuality)
        RatingRow(stringResource(R.string.review_professionalism), state.professionalism, viewModel::setProfessionalism)
        RatingRow(stringResource(R.string.review_communication), state.communication, viewModel::setCommunication)
        RatingRow(stringResource(R.string.review_attitude), state.attitude, viewModel::setAttitude)

        OutlinedTextField(
            value = state.content,
            onValueChange = viewModel::setContent,
            label = { Text(stringResource(R.string.review_content_label)) },
            placeholder = { Text(stringResource(R.string.review_content_hint)) },
            modifier = Modifier.fillMaxWidth(),
        )

        if (state.error == ReviewErrorKey.CONTENT_INVALID) {
            Text(text = stringResource(R.string.review_err_content))
        }
        if (state.error == ReviewErrorKey.SUBMIT_FAILED) {
            Text(text = stringResource(R.string.review_err_submit))
        }

        Button(
            onClick = { viewModel.submit(orderId, onSubmitted) },
            enabled = viewModel.canSubmit && !state.isSubmitting,
            modifier = Modifier.fillMaxWidth(),
        ) {
            if (state.isSubmitting) {
                CircularProgressIndicator(modifier = Modifier.padding(end = 8.dp))
            }
            Text(stringResource(R.string.review_submit))
        }
    }
}

@androidx.annotation.OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
private fun RatingRow(label: String, value: Int, onChange: (Int) -> Unit) {
    Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
        Text(text = label)
        Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            (1..5).forEach { star ->
                FilterChip(
                    selected = value >= star,
                    onClick = { onChange(star) },
                    label = { Text("$star") },
                )
            }
        }
    }
}
