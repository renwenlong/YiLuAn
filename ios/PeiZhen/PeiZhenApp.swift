import SwiftUI

@main
struct PeiZhenApp: App {
    @StateObject private var authViewModel = AuthViewModel()

    var body: some Scene {
        WindowGroup {
            Group {
                if authViewModel.isAuthenticated {
                    if authViewModel.currentUser?.role == nil {
                        RoleSelectionView()
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
        }
    }
}
