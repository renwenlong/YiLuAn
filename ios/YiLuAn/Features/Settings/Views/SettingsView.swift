import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @StateObject private var viewModel = SettingsViewModel()
    @State private var showClearCacheAlert = false
    @State private var showRoleSwitchAlert = false

    private var currentRole: UserRole? {
        authViewModel.currentUser?.role
    }

    private var switchTargetRole: UserRole {
        currentRole == .patient ? .companion : .patient
    }

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

            Section("角色") {
                Button {
                    showRoleSwitchAlert = true
                } label: {
                    HStack {
                        Label("切换为\(switchTargetRole == .patient ? "患者" : "陪诊师")", systemImage: "arrow.left.arrow.right")
                        Spacer()
                        Text(currentRole == .patient ? "当前：患者" : "当前：陪诊师")
                            .font(.dsCaption)
                            .foregroundStyle(Color.textHint)
                    }
                }
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
        .alert("切换角色", isPresented: $showRoleSwitchAlert) {
            Button("取消", role: .cancel) {}
            Button("切换") {
                Task { await authViewModel.switchRole(to: switchTargetRole) }
            }
        } message: {
            Text("确定要切换为\(switchTargetRole == .patient ? "患者" : "陪诊师")身份吗？")
        }
    }
}

#Preview {
    NavigationStack {
        SettingsView()
            .environmentObject(AuthViewModel())
    }
}
