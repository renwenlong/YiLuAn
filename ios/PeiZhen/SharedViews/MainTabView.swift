import SwiftUI

struct MainTabView: View {
    @EnvironmentObject var authViewModel: AuthViewModel

    var body: some View {
        TabView {
            if authViewModel.currentUser?.role == .patient {
                // Patient tabs
                PatientHomeView()
                    .tabItem {
                        Label("首页", systemImage: "house.fill")
                    }

                Text("我的订单")
                    .tabItem {
                        Label("订单", systemImage: "list.clipboard")
                    }

                Text("消息")
                    .tabItem {
                        Label("消息", systemImage: "message.fill")
                    }

                ProfileView()
                    .tabItem {
                        Label("我的", systemImage: "person.fill")
                    }
            } else {
                // Companion tabs
                CompanionHomeView()
                    .tabItem {
                        Label("首页", systemImage: "house.fill")
                    }

                Text("可接订单")
                    .tabItem {
                        Label("接单", systemImage: "tray.full.fill")
                    }

                Text("消息")
                    .tabItem {
                        Label("消息", systemImage: "message.fill")
                    }

                ProfileView()
                    .tabItem {
                        Label("我的", systemImage: "person.fill")
                    }
            }
        }
    }
}

#Preview {
    MainTabView()
        .environmentObject(AuthViewModel())
}
