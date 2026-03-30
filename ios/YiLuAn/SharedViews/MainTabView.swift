import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var authViewModel: AuthViewModel

    var body: some View {
        TabView {
            if authViewModel.currentUser?.role == .patient {
                PatientHomeView()
                    .tabItem { Label("首页", systemImage: "house.fill") }
                NavigationStack { OrderListView(isCompanion: false) }
                    .tabItem { Label("订单", systemImage: "list.clipboard") }
                ChatListView()
                    .tabItem { Label("消息", systemImage: "message.fill") }
                ProfileView()
                    .tabItem { Label("我的", systemImage: "person.fill") }
            } else {
                CompanionHomeView()
                    .tabItem { Label("首页", systemImage: "house.fill") }
                AvailableOrdersView()
                    .tabItem { Label("接单", systemImage: "tray.full.fill") }
                ChatListView()
                    .tabItem { Label("消息", systemImage: "message.fill") }
                ProfileView()
                    .tabItem { Label("我的", systemImage: "person.fill") }
            }
        }
    }
}

#Preview {
    MainTabView()
        .environmentObject(AuthViewModel())
}
