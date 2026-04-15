import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @StateObject private var viewModel = SettingsViewModel()
    @State private var showClearCacheAlert = false

    var body: some View {
        List {
            Section("通用") {
                NavigationLink {
                    PrivacyPolicyView()
                } label: {
                    Label("隐私政策", systemImage: "lock.shield")
                }

                NavigationLink {
                    TermsOfServiceView()
                } label: {
                    Label("用户协议", systemImage: "doc.text")
                }

                HStack {
                    Label("清除缓存", systemImage: "trash")
                    Spacer()
                    Text(viewModel.cacheSize)
                        .foregroundStyle(Color.textHint)
                }
                .contentShape(Rectangle())
                .onTapGesture { showClearCacheAlert = true }
            }

            Section("关于") {
                HStack {
                    Text("版本")
                    Spacer()
                    Text(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0")
                        .foregroundStyle(Color.textHint)
                }
            }

            Section {
                NavigationLink {
                    DeleteAccountView()
                } label: {
                    Label("注销账号", systemImage: "person.crop.circle.badge.minus")
                        .foregroundStyle(Color.danger)
                }
            }
        }
        .navigationTitle("设置")
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { viewModel.calculateCacheSize() }
        .alert("清除缓存", isPresented: $showClearCacheAlert) {
            Button("取消", role: .cancel) {}
            Button("清除", role: .destructive) { viewModel.clearCache() }
        } message: {
            Text("确定要清除缓存吗？当前缓存大小：\(viewModel.cacheSize)")
        }
    }
}

#Preview {
    NavigationStack {
        SettingsView()
            .environmentObject(AuthViewModel())
    }
}
