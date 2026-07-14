import SwiftUI

struct ProfileView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @EnvironmentObject var loc: LocalizationManager

    private var isCompanion: Bool {
        authViewModel.currentUser?.role == .companion
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 0) {
                    // Hero header with gradient
                    ZStack(alignment: .bottomLeading) {
                        AppGradient.primary
                            .frame(height: 180)
                            .ignoresSafeArea(edges: .top)

                        HStack(spacing: Spacing.lg) {
                            // Avatar
                            ZStack {
                                Circle()
                                    .fill(AppGradient.primary)
                                    .frame(width: 64, height: 64)

                                Text(String(authViewModel.currentUser?.displayName?.prefix(1) ?? Character(loc.t("profile.avatarFallback"))))
                                    .font(.dsH1)
                                    .foregroundStyle(.white)
                            }
                            .overlay(
                                Circle()
                                    .stroke(.white, lineWidth: 3)
                            )
                            .shadow(color: .black.opacity(0.15), radius: 8, x: 0, y: 4)

                            VStack(alignment: .leading, spacing: 4) {
                                Text(authViewModel.currentUser?.displayName ?? loc.t("profile.nicknameNotSet"))
                                    .font(.dsTitle)
                                    .foregroundStyle(.white)

                                if let phone = authViewModel.currentUser?.phone {
                                    Text(phone)
                                        .font(.dsSubheadline)
                                        .foregroundStyle(.white.opacity(0.7))
                                }
                            }

                            Spacer()

                            if isCompanion {
                                Text(loc.t("role.companion"))
                                    .font(.dsSmall)
                                    .fontWeight(.medium)
                                    .foregroundStyle(.white)
                                    .padding(.horizontal, 10)
                                    .padding(.vertical, 4)
                                    .background(.white.opacity(0.2))
                                    .clipShape(Capsule())
                            }
                        }
                        .padding(.horizontal, Spacing.xl)
                        .padding(.bottom, Spacing.xl)
                    }

                    VStack(spacing: Spacing.md) {
                        // Account section
                        VStack(spacing: 0) {
                            MenuRow(icon: "person.crop.circle", title: loc.t("profile.profile")) {
                                ProfileEditView()
                            }

                            if isCompanion {
                                Divider().padding(.leading, 52)
                                MenuRow(icon: "stethoscope", title: loc.t("profile.companionHomepage")) {
                                    CompanionSelfProfileView()
                                }
                            }

                            Divider().padding(.leading, 52)
                            MenuRow(icon: "phone.badge.checkmark", title: loc.t("bindPhone.bindPhone")) {
                                BindPhoneView()
                            }

                            Divider().padding(.leading, 52)
                            MenuRow(icon: "wallet.pass", title: loc.t("profile.menuWallet")) {
                                WalletView()
                            }

                            Divider().padding(.leading, 52)
                            MenuRow(icon: "person.2", title: loc.t("profile.menuFamily")) {
                                FamilyMembersView()
                            }

                            Divider().padding(.leading, 52)
                            MenuRow(icon: "phone.circle.fill", title: loc.t("order.emergencyContact")) {
                                EmergencyContactsView()
                            }

                            Divider().padding(.leading, 52)
                            MenuRow(icon: "bell.badge", title: loc.t("profile.menuFollowup")) {
                                FollowupRemindersView()
                            }
                        }
                        .background(Color.bgCard)
                        .cornerRadius(CornerRadius.lg)
                        .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
                        .padding(.horizontal, Spacing.lg)

                        // Features section
                        VStack(spacing: 0) {
                            MenuRow(icon: "bell.badge", title: loc.t("profile.messageNotifications")) {
                                NotificationListView()
                            }

                            Divider().padding(.leading, 52)
                            MenuRow(icon: "gearshape", title: loc.t("settings.title")) {
                                SettingsView()
                            }

                            Divider().padding(.leading, 52)
                            MenuRow(icon: "info.circle", title: loc.t("profile.aboutUs")) {
                                AboutView()
                            }
                        }
                        .background(Color.bgCard)
                        .cornerRadius(CornerRadius.lg)
                        .shadow(color: .black.opacity(0.05), radius: 4, x: 0, y: 2)
                        .padding(.horizontal, Spacing.lg)

                        // Logout button
                        Button {
                            authViewModel.signOut()
                        } label: {
                            Text(loc.t("settings.logout"))
                                .font(.dsBody)
                                .foregroundStyle(Color.danger)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 14)
                        }
                        .background(Color.bgCard)
                        .cornerRadius(CornerRadius.lg)
                        .overlay(
                            RoundedRectangle(cornerRadius: CornerRadius.lg)
                                .stroke(Color.danger.opacity(0.2), lineWidth: 1)
                        )
                        .padding(.horizontal, Spacing.lg)
                        .padding(.top, Spacing.sm)
                    }
                    .padding(.top, Spacing.lg)
                    .padding(.bottom, 120)
                }
            }
            .background(Color.bgPage)
            .ignoresSafeArea(edges: .top)
            .navigationTitle("")
            .navigationBarHidden(true)
        }
    }
}

// MARK: - Menu Row Component

private struct MenuRow<Destination: View>: View {
    let icon: String
    let title: String
    @ViewBuilder let destination: () -> Destination

    var body: some View {
        NavigationLink {
            destination()
        } label: {
            HStack(spacing: Spacing.md) {
                Image(systemName: icon)
                    .font(.system(size: 18))
                    .foregroundStyle(Color.textSecondary)
                    .frame(width: 28)

                Text(title)
                    .font(.dsBody)
                    .foregroundStyle(Color.textPrimary)

                Spacer()

                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .semibold))
                    .foregroundStyle(Color.textHint)
            }
            .padding(.horizontal, Spacing.lg)
            .padding(.vertical, 14)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    ProfileView()
        .environmentObject(AuthViewModel())
}
