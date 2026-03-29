import SwiftUI

struct ProfileView: View {
    @EnvironmentObject var authViewModel: AuthViewModel

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

                // Settings
                Section("设置") {
                    NavigationLink("个人资料") {
                        Text("编辑资料 — Phase 2")
                    }
                    NavigationLink("通知设置") {
                        Text("通知设置 — Phase 6")
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
