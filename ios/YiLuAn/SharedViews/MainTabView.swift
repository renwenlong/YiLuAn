import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var loc: LocalizationManager
    @EnvironmentObject var authViewModel: AuthViewModel

    var body: some View {
        TabView {
            if authViewModel.currentUser?.role == .patient {
                PatientHomeView()
                    .tabItem { Label(loc.t("tabBar.home"), systemImage: "house.fill") }
                NavigationStack { OrderListView(isCompanion: false) }
                    .tabItem { Label(loc.t("tabBar.orders"), systemImage: "list.clipboard") }
                ChatListView()
                    .tabItem { Label(loc.t("tabBar.chat"), systemImage: "message.fill") }
                ProfileView()
                    .tabItem { Label(loc.t("tabBar.profile"), systemImage: "person.fill") }
            } else {
                CompanionHomeView()
                    .tabItem { Label(loc.t("tabBar.home"), systemImage: "house.fill") }
                AvailableOrdersView()
                    .tabItem { Label(loc.t("tabBar.availableOrders"), systemImage: "tray.full.fill") }
                ChatListView()
                    .tabItem { Label(loc.t("tabBar.chat"), systemImage: "message.fill") }
                ProfileView()
                    .tabItem { Label(loc.t("tabBar.profile"), systemImage: "person.fill") }
            }
        }
    }
}

#Preview {
    MainTabView()
        .environmentObject(AuthViewModel())
}
