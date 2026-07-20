package com.yiluan.ui

import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.yiluan.feature.auth.AuthScreen
import com.yiluan.feature.order.CreateOrderScreen
import com.yiluan.feature.order.OrderDetailScreen
import com.yiluan.feature.order.OrderListScreen
import com.yiluan.feature.order.PatientHomeScreen
import com.yiluan.feature.profile.BindPhoneScreen
import com.yiluan.feature.profile.EmergencyContactsScreen
import com.yiluan.feature.profile.FamilyMembersScreen
import com.yiluan.feature.profile.LegalDoc
import com.yiluan.feature.profile.LegalScreen
import com.yiluan.feature.profile.SettingsScreen
import com.yiluan.feature.profile.WalletScreen
import com.yiluan.feature.review.ReviewScreen

/**
 * 应用导航宿主（单 Activity + Navigation-Compose）。
 * ANDROID-DEV-B0-CORE — 骨架 splash。
 * ANDROID-DEV-B1-AUTH — auth 登录流程 + splash 按 token 路由。
 * ANDROID-DEV-B2-PATIENT — 患者闭环: home/create-order/order-list/order-detail。
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
                    PatientHomeScreen(
                        onCreateOrder = { navController.navigate(Routes.CREATE_ORDER) },
                        onMyOrders = { navController.navigate(Routes.ORDER_LIST) },
                        onSettings = { navController.navigate(Routes.SETTINGS) },
                    )
                }
                composable(Routes.CREATE_ORDER) {
                    CreateOrderScreen(
                        onCreated = { order ->
                            navController.navigate(Routes.orderDetail(order.id)) {
                                popUpTo(Routes.CREATE_ORDER) { inclusive = true }
                            }
                        },
                    )
                }
                composable(Routes.ORDER_LIST) {
                    OrderListScreen(
                        isCompanion = false,
                        onOrderClick = { orderId ->
                            navController.navigate(Routes.orderDetail(orderId))
                        },
                    )
                }
                composable(
                    route = Routes.ORDER_DETAIL,
                    arguments = listOf(navArgument(Routes.ARG_ORDER_ID) { type = NavType.StringType }),
                ) { backStackEntry ->
                    val orderId = backStackEntry.arguments?.getString(Routes.ARG_ORDER_ID).orEmpty()
                    OrderDetailScreen(orderId = orderId, isCompanion = false)
                }

                // ── B6 长尾 ──
                composable(Routes.SETTINGS) {
                    SettingsScreen(
                        onPrivacy = { navController.navigate(Routes.LEGAL_PRIVACY) },
                        onTerms = { navController.navigate(Routes.LEGAL_TERMS) },
                        onAccountDeleted = {
                            navController.navigate(Routes.AUTH) {
                                popUpTo(0) { inclusive = true }
                            }
                        },
                    )
                }
                composable(Routes.FAMILY_MEMBERS) { FamilyMembersScreen() }
                composable(Routes.EMERGENCY_CONTACTS) { EmergencyContactsScreen() }
                composable(Routes.WALLET) { WalletScreen() }
                composable(Routes.BIND_PHONE) {
                    BindPhoneScreen(onBound = { navController.popBackStack() })
                }
                composable(Routes.LEGAL_PRIVACY) { LegalScreen(doc = LegalDoc.PRIVACY) }
                composable(Routes.LEGAL_TERMS) { LegalScreen(doc = LegalDoc.TERMS) }
                composable(
                    route = Routes.REVIEW,
                    arguments = listOf(navArgument(Routes.ARG_ORDER_ID) { type = NavType.StringType }),
                ) { backStackEntry ->
                    val orderId = backStackEntry.arguments?.getString(Routes.ARG_ORDER_ID).orEmpty()
                    ReviewScreen(orderId = orderId, onSubmitted = { navController.popBackStack() })
                }
            }
        }
    }
}

/**
 * 启动屏：查本地 token 决定去登录还是主界面。
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
