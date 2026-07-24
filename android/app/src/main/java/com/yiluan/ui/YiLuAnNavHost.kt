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
import com.yiluan.feature.chat.ChatListScreen
import com.yiluan.feature.chat.ChatRoomScreen
import com.yiluan.feature.companion.AvailableOrdersScreen
import com.yiluan.feature.companion.CompanionDetailScreen
import com.yiluan.feature.companion.CompanionHomeScreen
import com.yiluan.feature.companion.CompanionSelfProfileScreen
import com.yiluan.feature.companion.CompanionSetupScreen
import com.yiluan.feature.companion.TodayOrdersScreen
import com.yiluan.feature.notification.NotificationListScreen
import com.yiluan.feature.order.CreateOrderScreen
import com.yiluan.feature.order.OrderDetailScreen
import com.yiluan.feature.order.PaymentResultScreen
import com.yiluan.feature.order.OrderListScreen
import com.yiluan.feature.order.PatientHomeScreen
import com.yiluan.feature.precheck.PrecheckSummaryScreen
import com.yiluan.feature.share.ShareManageScreen
import com.yiluan.feature.share.ShareOtpScreen
import com.yiluan.feature.profile.BindPhoneScreen
import com.yiluan.feature.profile.EmergencyContactsScreen
import com.yiluan.feature.profile.AboutScreen
import com.yiluan.feature.profile.FamilyMembersScreen
import com.yiluan.feature.profile.FollowupRemindersScreen
import com.yiluan.feature.profile.ProfileEditScreen
import com.yiluan.feature.profile.ProfileScreen
import com.yiluan.feature.profile.LegalDoc
import com.yiluan.feature.profile.LegalScreen
import com.yiluan.feature.profile.SettingsScreen
import com.yiluan.feature.profile.WalletScreen
import com.yiluan.feature.review.ReviewScreen

/**
 * 应用导航宿主（单 Activity + Navigation-Compose）。
 * B0 splash / B1 auth / B2 患者闭环 / B6 长尾 / B4 实时 / B3 陪诊员闭环。
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
                        onCompanionMode = { navController.navigate(Routes.COMPANION_HOME) },
                        onChat = { navController.navigate(Routes.CHAT_LIST) },
                        onNotifications = { navController.navigate(Routes.NOTIFICATIONS) },
                        onProfile = { navController.navigate(Routes.PROFILE) },
                    )
                }
                composable(Routes.PROFILE) {
                    ProfileScreen(
                        onEditProfile = { navController.navigate(Routes.PROFILE_EDIT) },
                        onBindPhone = { navController.navigate(Routes.BIND_PHONE) },
                        onWallet = { navController.navigate(Routes.WALLET) },
                        onFamily = { navController.navigate(Routes.FAMILY_MEMBERS) },
                        onEmergency = { navController.navigate(Routes.EMERGENCY_CONTACTS) },
                        onFollowups = { navController.navigate(Routes.FOLLOWUP_REMINDERS) },
                        onNotifications = { navController.navigate(Routes.NOTIFICATIONS) },
                        onSettings = { navController.navigate(Routes.SETTINGS) },
                        onAbout = { navController.navigate(Routes.ABOUT) },
                        onCompanionHome = { navController.navigate(Routes.COMPANION_PROFILE) },
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
                    OrderDetailScreen(
                        orderId = orderId,
                        isCompanion = false,
                        onNavigateToPayResult = { success ->
                            navController.navigate(Routes.payResult(orderId, success))
                        },
                        onReview = { navController.navigate(Routes.review(orderId)) },
                        onShare = { navController.navigate(Routes.shareManage(orderId)) },
                    )
                }
                composable(
                    route = Routes.PAY_RESULT,
                    arguments = listOf(
                        navArgument(Routes.ARG_ORDER_ID) { type = NavType.StringType },
                        navArgument(Routes.ARG_PAY_OUTCOME) { type = NavType.StringType },
                    ),
                ) { backStackEntry ->
                    val orderId = backStackEntry.arguments?.getString(Routes.ARG_ORDER_ID).orEmpty()
                    val success = backStackEntry.arguments?.getString(Routes.ARG_PAY_OUTCOME) == "success"
                    PaymentResultScreen(
                        isSuccess = success,
                        onViewOrder = { navController.popBackStack() },
                        onGoHome = {
                            navController.navigate(Routes.HOME) { popUpTo(Routes.HOME) { inclusive = true } }
                        },
                        onRetry = { navController.popBackStack() },
                    )
                }

                // ── B6 长尾 ──
                composable(Routes.SETTINGS) {
                    SettingsScreen(
                        onPrivacy = { navController.navigate(Routes.LEGAL_PRIVACY) },
                        onTerms = { navController.navigate(Routes.LEGAL_TERMS) },
                        onFollowups = { navController.navigate(Routes.FOLLOWUP_REMINDERS) },
                        onEditProfile = { navController.navigate(Routes.PROFILE_EDIT) },
                        onAbout = { navController.navigate(Routes.ABOUT) },
                        onAccountDeleted = {
                            navController.navigate(Routes.AUTH) {
                                popUpTo(0) { inclusive = true }
                            }
                        },
                    )
                }
                composable(Routes.FAMILY_MEMBERS) { FamilyMembersScreen() }
                composable(Routes.FOLLOWUP_REMINDERS) { FollowupRemindersScreen() }
                composable(Routes.PROFILE_EDIT) {
                    ProfileEditScreen(onSaved = { navController.popBackStack() })
                }
                composable(Routes.ABOUT) { AboutScreen() }
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

                // ── B4 实时 ──
                composable(Routes.CHAT_LIST) {
                    ChatListScreen(
                        onConversationClick = { orderId -> navController.navigate(Routes.chatRoom(orderId)) },
                    )
                }
                composable(
                    route = Routes.CHAT_ROOM,
                    arguments = listOf(navArgument(Routes.ARG_ORDER_ID) { type = NavType.StringType }),
                ) { backStackEntry ->
                    val oid = backStackEntry.arguments?.getString(Routes.ARG_ORDER_ID).orEmpty()
                    ChatRoomScreen(orderId = oid)
                }
                composable(Routes.NOTIFICATIONS) { NotificationListScreen() }

                // ── B3 陪诊员闭环 ──
                composable(Routes.COMPANION_HOME) {
                    CompanionHomeScreen(
                        onAvailableOrders = { navController.navigate(Routes.COMPANION_AVAILABLE) },
                        onTodayOrders = { navController.navigate(Routes.COMPANION_TODAY) },
                        onSetup = { navController.navigate(Routes.COMPANION_SETUP) },
                        onProfile = { navController.navigate(Routes.COMPANION_PROFILE) },
                    )
                }
                composable(Routes.COMPANION_AVAILABLE) {
                    AvailableOrdersScreen(
                        onOrderClick = { orderId -> navController.navigate(Routes.orderDetail(orderId)) },
                    )
                }
                composable(Routes.COMPANION_TODAY) {
                    TodayOrdersScreen(
                        onOrderClick = { orderId -> navController.navigate(Routes.orderDetail(orderId)) },
                    )
                }
                composable(Routes.COMPANION_SETUP) {
                    CompanionSetupScreen(onApplied = { navController.popBackStack() })
                }
                composable(Routes.COMPANION_PROFILE) {
                    CompanionSelfProfileScreen(
                        onEdit = { navController.navigate(Routes.PROFILE_EDIT) },
                    )
                }
                composable(
                    route = Routes.COMPANION_DETAIL,
                    arguments = listOf(navArgument(Routes.ARG_COMPANION_ID) { type = NavType.StringType }),
                ) { backStackEntry ->
                    val companionId = backStackEntry.arguments?.getString(Routes.ARG_COMPANION_ID).orEmpty()
                    CompanionDetailScreen(companionId = companionId)
                }

                // ── B5 Precheck + Share ──
                composable(
                    route = Routes.PRECHECK,
                    arguments = listOf(navArgument(Routes.ARG_ORDER_ID) { type = NavType.StringType }),
                ) { e ->
                    val oid = e.arguments?.getString(Routes.ARG_ORDER_ID).orEmpty()
                    PrecheckSummaryScreen(orderId = oid)
                }
                composable(
                    route = Routes.SHARE_MANAGE,
                    arguments = listOf(navArgument(Routes.ARG_ORDER_ID) { type = NavType.StringType }),
                ) { e ->
                    val oid = e.arguments?.getString(Routes.ARG_ORDER_ID).orEmpty()
                    ShareManageScreen(orderId = oid)
                }
                composable(
                    route = Routes.SHARE_OTP,
                    arguments = listOf(navArgument(Routes.ARG_TOKEN) { type = NavType.StringType }),
                ) { e ->
                    val t = e.arguments?.getString(Routes.ARG_TOKEN).orEmpty()
                    ShareOtpScreen(token = t)
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
