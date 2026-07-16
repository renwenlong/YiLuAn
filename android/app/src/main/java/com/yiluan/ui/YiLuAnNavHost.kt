package com.yiluan.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController

/**
 * 应用导航宿主（单 Activity + Navigation-Compose）。
 * ANDROID-DEV-B0-CORE — B0 骨架：仅 splash 起始目的地，验证导航贯通。
 * 后续批次在此挂 login/role-select/patient/companion 等目的地。
 */
@Composable
fun YiLuAnNavHost() {
    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            val navController = rememberNavController()
            NavHost(
                navController = navController,
                startDestination = Routes.SPLASH,
            ) {
                composable(Routes.SPLASH) {
                    SplashScreen()
                }
            }
        }
    }
}

@Composable
private fun SplashScreen() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = "医路安")
    }
}
