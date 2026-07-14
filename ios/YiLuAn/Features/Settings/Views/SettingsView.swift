import SwiftUI

struct SettingsView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @EnvironmentObject var loc: LocalizationManager
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
            Section(loc.t("settings.general")) {
                NavigationLink {
                    PrivacyPolicyView()
                } label: {
                    Label(loc.t("settings.privacyPolicy"), systemImage: "lock.shield")
                }

                NavigationLink {
                    TermsOfServiceView()
                } label: {
                    Label(loc.t("settings.termsOfService"), systemImage: "doc.text")
                }

                HStack {
                    Label(loc.t("settings.clearCache"), systemImage: "trash")
                    Spacer()
                    Text(viewModel.cacheSize)
                        .foregroundStyle(Color.textHint)
                }
                .contentShape(Rectangle())
                .onTapGesture { showClearCacheAlert = true }
            }

            // I18N-DEV-003 (ADR-0063 §5.3)：语言切换入口。
            // 本 Section 文案用 loc.t() 直接 i18n（新代码）；现有硬编码中文 003B 抽 key。
            Section(loc.t("settings.language")) {
                ForEach(LocalizationManager.Language.allCases) { lang in
                    Button {
                        loc.setLanguage(lang)
                    } label: {
                        HStack {
                            Text(lang.displayName)
                                .foregroundStyle(Color.textPrimary)
                            Spacer()
                            if lang == loc.currentLanguage {
                                Image(systemName: "checkmark")
                                    .foregroundStyle(Color.primary)
                            }
                        }
                        .contentShape(Rectangle())
                    }
                }
            }

            Section(loc.t("settings.role")) {
                Button {
                    showRoleSwitchAlert = true
                } label: {
                    HStack {
                        Label(loc.t("settings.switchToRole", loc.t(switchTargetRole == .patient ? "role.patient" : "role.companion")), systemImage: "arrow.left.arrow.right")
                        Spacer()
                        Text(currentRole == .patient ? loc.t("settings.currentPatient") : loc.t("settings.currentCompanion"))
                            .font(.dsCaption)
                            .foregroundStyle(Color.textHint)
                    }
                }
            }

            Section(loc.t("settings.about")) {
                HStack {
                    Text(loc.t("settings.version"))
                    Spacer()
                    Text(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0")
                        .foregroundStyle(Color.textHint)
                }
            }

            Section {
                NavigationLink {
                    DeleteAccountView()
                } label: {
                    Label(loc.t("settings.deleteAccount"), systemImage: "person.crop.circle.badge.minus")
                        .foregroundStyle(Color.danger)
                }
            }
        }
        .navigationTitle(loc.t("settings.title"))
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { viewModel.calculateCacheSize() }
        .alert(loc.t("settings.clearCache"), isPresented: $showClearCacheAlert) {
            Button(loc.t("common.cancel"), role: .cancel) {}
            Button(loc.t("settings.clear"), role: .destructive) { viewModel.clearCache() }
        } message: {
            Text(loc.t("settings.confirmClearCache", viewModel.cacheSize))
        }
        .alert(loc.t("dialog.switchRoleTitle"), isPresented: $showRoleSwitchAlert) {
            Button(loc.t("common.cancel"), role: .cancel) {}
            Button(loc.t("settings.switch")) {
                Task { await authViewModel.switchRole(to: switchTargetRole) }
            }
        } message: {
            Text(loc.t("settings.confirmSwitchRole", loc.t(switchTargetRole == .patient ? "role.patient" : "role.companion")))
        }
    }
}

#Preview {
    NavigationStack {
        SettingsView()
            .environmentObject(AuthViewModel())
    }
}
