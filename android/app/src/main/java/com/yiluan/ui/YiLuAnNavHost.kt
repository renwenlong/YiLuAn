package com.yiluan.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.yiluan.feature.auth.AuthScreen

/**
 * 应用导航宿主（单 Activity + Navigation-Compose）。
 * ANDROID-DEV-B0-CORE — 骨架：splash 起始目的地。
 * ANDROID-DEV-B1-AUTH — 挂 auth（登录流程）+ home 占位；splash 按 token 决定去向。
 */
@Composable
fun YiLuAnNavHost(
    startDestination: String = Routes.SPLASH,
) {
    MaterialTheme {
        Surface(modifier = Modifier.fillMaxSize()) {
            val navController = rememberNavController()
            NavHost(
                navController = navController,
                startDestination = startDestination,
            ) {
                composable(Routes.SPLASH) {
                    SplashScreen(navController)
                }
                composable(Routes.AUTH) {
                    AuthScreen(
                        onAuthenticated = {
                            navController.navigate(Routes.HOME) {
                                popUpTo(Routes.AUTH) { inclusive = true }
                            }
                        },
                    )
                }
                composable(Routes.HOME) {
                    HomePlaceholderScreen()
                }
            }
        }
    }
}

/**
 * 启动屏：查本地 token 决定去登录还是主界面。
 * 有 token → HOME；无 → AUTH。
 */
@Composable
private fun SplashScreen(
    navController: NavHostController,
    viewModel: SplashViewModel = hiltViewModel(),
) {
    LaunchedEffect(Unit) {
        val dest = if (viewModel.hasToken()) Routes.HOME else Routes.AUTH
        navController.navigate(dest) {
            popUpTo(Routes.SPLASH) { inclusive = true }
        }
    }
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        CircularProgressIndicator()
    }
}

/** 登录后主界面占位（患者/陪诊员真实 home 在 B2/B3 落地）。 */
@Composable
private fun HomePlaceholderScreen() {
    Box(
        modifier = Modifier.fillMaxSize(),
        contentAlignment = Alignment.Center,
    ) {
        Text(text = "医路安")
    }
}
