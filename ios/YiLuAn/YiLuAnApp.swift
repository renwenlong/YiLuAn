import SwiftUI

@main
struct YiLuAnApp: App {
    @StateObject private var authViewModel = AuthViewModel()
    @StateObject private var localizationManager = LocalizationManager.shared

    /// S2-INT-006 #2：share deep link 截获后的待处理 token（用 sheet 弹 ShareOTPView）
    @State private var pendingShareToken: String?

    var body: some Scene {
        WindowGroup {
            Group {
                if authViewModel.isAuthenticated {
                    if authViewModel.currentUser?.role == nil {
                        RoleSelectionView()
                            .environmentObject(authViewModel)
                    } else if authViewModel.currentUser?.displayName == nil || authViewModel.currentUser?.displayName?.isEmpty == true {
                        ProfileSetupView()
                            .environmentObject(authViewModel)
                    } else {
                        MainTabView()
                            .environmentObject(authViewModel)
                    }
                } else {
                    LoginView()
                        .environmentObject(authViewModel)
                }
            }
            // S2-INT-006 #2：UniversalLink + URL scheme 截获
            .onOpenURL { url in
                if let token = ShareDeepLink.parse(url) {
                    pendingShareToken = token
                }
            }
            .onContinueUserActivity(NSUserActivityTypeBrowsingWeb) { activity in
                if let url = activity.webpageURL,
                   let token = ShareDeepLink.parse(url) {
                    pendingShareToken = token
                }
            }
            // share token 解析成功 → sheet 弹 ShareOTPView（无论 App 当前何种登录态）
            .sheet(
                isPresented: Binding(
                    get: { pendingShareToken != nil },
                    set: { if !$0 { pendingShareToken = nil } }
                )
            ) {
                if let token = pendingShareToken {
                    ShareOTPView(shareToken: token) { _, _ in
                        // 验证成功 → ShareOTPView 自身已 push ShareOrderView，无额外动作
                    }
                }
            }
            // I18N-DEV-003 (ADR-0063 §5.2)：根视图注入 LocalizationManager，
            // currentLanguage 变更驱动 SwiftUI 重渲染（即时切换无需重启）。
            .environmentObject(localizationManager)
            .environment(\.locale, Locale(identifier: localizationManager.currentLanguage.rawValue))
        }
    }
}
