import SwiftUI

struct ProfileView: View {
    @EnvironmentObject var authViewModel: AuthViewModel

    private var isCompanion: Bool {
        authViewModel.currentUser?.role == .companion
    }

    var body: some View {
        NavigationStack {
            List {
                // User info section
                Section {
                    HStack(spacing: 16) {
                        Image(systemName: "person.circle.fill")
                            .font(.system(size: 50))
                            .foregroundStyle(.gray)

                        VStack(alignment: .leading) {
                            Text(authViewModel.currentUser?.displayName ?? "未设置昵称")
                                .font(.headline)
                            Text(authViewModel.currentUser?.phone ?? "")
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 4)
                }

                // Profile & account
                Section("账号") {
                    NavigationLink("个人资料") {
                        ProfileEditView()
                    }
                    if isCompanion {
                        NavigationLink("陪诊师主页") {
                            CompanionSelfProfileView()
                        }
                    }
                    NavigationLink("绑定手机号") {
                        BindPhoneView()
                    }
                    NavigationLink("我的钱包") {
                        WalletView()
                    }
                }

                // Features
                Section("功能") {
                    NavigationLink("消息通知") {
                        NotificationListView()
                    }
                    NavigationLink {
                        SettingsView()
                    } label: {
                        Label("设置", systemImage: "gearshape")
                    }
                    NavigationLink {
                        AboutView()
                    } label: {
                        Label("关于我们", systemImage: "info.circle")
                    }
                }

                // Sign out
                Section {
                    Button("退出登录", role: .destructive) {
                        authViewModel.signOut()
                    }
                }
            }
            .navigationTitle("我的")
        }
    }
}

#Preview {
    ProfileView()
        .environmentObject(AuthViewModel())
}
