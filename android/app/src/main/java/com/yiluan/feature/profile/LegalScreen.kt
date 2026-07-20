package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.yiluan.R

/** 法务文档类型。 */
enum class LegalDoc { PRIVACY, TERMS }

/**
 * 法务文档屏（隐私政策 / 服务条款）——纯静态文案，无 API。
 * ANDROID-DEV-B6-LONGTAIL — 对齐 iOS PrivacyPolicyView/TermsOfServiceView。
 */
@Composable
fun LegalScreen(
    doc: LegalDoc,
    modifier: Modifier = Modifier,
) {
    val titleRes = if (doc == LegalDoc.PRIVACY) R.string.legal_privacy_title else R.string.legal_terms_title
    val bodyRes = if (doc == LegalDoc.PRIVACY) R.string.legal_privacy_body else R.string.legal_terms_body

    Column(
        modifier = modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(24.dp),
    ) {
        Text(text = stringResource(titleRes))
        Text(
            text = stringResource(bodyRes),
            modifier = Modifier.padding(top = 12.dp),
        )
    }
}
