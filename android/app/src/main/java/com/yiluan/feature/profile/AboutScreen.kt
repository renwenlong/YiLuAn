package com.yiluan.feature.profile

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.unit.dp
import com.yiluan.BuildConfig
import com.yiluan.R

/**
 * 关于页：App 版本 + 公司信息（纯静态，无 API）。
 * ANDROID-DEV-GAP-PROFILE-ABOUT — 补漏页，对齐小程序 profile/about + iOS AboutView。
 */
@Composable
fun AboutScreen(
    modifier: Modifier = Modifier,
) {
    Column(
        modifier = modifier.fillMaxSize().padding(24.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(text = stringResource(R.string.about_title))
        Text(
            text = stringResource(R.string.about_version, BuildConfig.VERSION_NAME),
        )
        Text(text = stringResource(R.string.about_company))
    }
}
