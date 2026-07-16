package com.yiluan

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import com.yiluan.ui.YiLuAnNavHost
import dagger.hilt.android.AndroidEntryPoint

/**
 * 单 Activity 宿主。
 * ANDROID-DEV-B0-CORE — Compose + Navigation 单 Activity 架构（design §1§2）。
 */
@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            YiLuAnNavHost()
        }
    }
}
