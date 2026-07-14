import SwiftUI

struct DeleteAccountView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @StateObject private var viewModel = SettingsViewModel()
    @EnvironmentObject var loc: LocalizationManager
    @State private var showResult = false

    var body: some View {
        ScrollView {
            VStack(spacing: Spacing.xl) {
                // Warning header
                VStack(spacing: Spacing.sm) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 48))
                        .foregroundStyle(Color.warning)
                    Text(loc.t("settings.deleteAccount"))
                        .font(.title2.bold())
                    Text(loc.t("settings.irreversibleWarning"))
                        .font(.dsSubheadline)
                        .foregroundStyle(Color.textHint)
                }
                .padding(.top, Spacing.xl)

                // Data card
                VStack(alignment: .leading, spacing: Spacing.md) {
                    Text(loc.t("settings.dataToBeDeleted"))
                        .font(.dsHeadline)
                    dataRow(loc.t("settings.orderAndTransactionData"))
                    dataRow(loc.t("settings.profileAndCertInfo"))
                    dataRow(loc.t("settings.walletAndPaymentInfo"))
                    dataRow(loc.t("settings.chatHistory"))
                    dataRow(loc.t("settings.companionCertMaterials"))
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(CornerRadius.lg)

                // Recovery notice
                HStack {
                    Image(systemName: "info.circle.fill")
                        .foregroundStyle(Color.warning)
                    Text(loc.t("settings.recoverWithin30Days"))
                        .font(.dsSubheadline)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.warning.opacity(0.1))
                .cornerRadius(CornerRadius.md)

                // OTP verification
                VStack(alignment: .leading, spacing: Spacing.md) {
                    Text(loc.t("settings.verifyIdentity"))
                        .font(.dsHeadline)

                    HStack {
                        TextField(loc.t("settings.enter6DigitCode"), text: $viewModel.otpCode)
                            .keyboardType(.numberPad)
                            .textContentType(.oneTimeCode)
                            .onChange(of: viewModel.otpCode) { _, newValue in
                                if newValue.count > 6 {
                                    viewModel.otpCode = String(newValue.prefix(6))
                                }
                            }

                        Button {
                            guard let phone = authViewModel.currentUser?.phone else { return }
                            Task { await viewModel.sendOTP(phone: phone) }
                        } label: {
                            Text(viewModel.otpCountdown > 0 ? "\(viewModel.otpCountdown)s" : loc.t("settings.sendCode"))
                                .font(.dsSubheadline)
                        }
                        .disabled(!viewModel.canSendOTP)
                    }
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(CornerRadius.md)
                }

                // Confirmation checkbox
                Button {
                    viewModel.isConfirmed.toggle()
                } label: {
                    HStack(alignment: .top, spacing: Spacing.sm) {
                        Image(systemName: viewModel.isConfirmed ? "checkmark.square.fill" : "square")
                            .foregroundStyle(viewModel.isConfirmed ? Color.brand : Color.textHint)
                        Text(loc.t("settings.confirmAccountDeletion"))
                            .font(.dsSubheadline)
                            .foregroundStyle(Color.textSecondary)
                            .multilineTextAlignment(.leading)
                    }
                }

                // Long-press delete button
                longPressDeleteButton

                if let error = viewModel.errorMessage {
                    Text(error)
                        .font(.dsCaption)
                        .foregroundStyle(Color.danger)
                }
            }
            .padding()
        }
        .navigationTitle(loc.t("settings.deleteAccount"))
        .navigationBarTitleDisplayMode(.inline)
        .onDisappear { viewModel.cleanup() }
    }

    private var longPressDeleteButton: some View {
        Button {} label: {
            ZStack {
                RoundedRectangle(cornerRadius: CornerRadius.lg)
                    .fill(viewModel.canDelete ? Color.danger : Color.danger.opacity(0.3))

                if viewModel.isPressing {
                    GeometryReader { geo in
                        RoundedRectangle(cornerRadius: CornerRadius.lg)
                            .fill(Color.danger.opacity(0.3))
                            .frame(width: geo.size.width * CGFloat(3 - viewModel.pressCountdown) / 3.0)
                    }
                }

                Text(viewModel.isPressing ? loc.t("settings.holdCountdown", viewModel.pressCountdown) : loc.t("deleteAccount.longPress"))
                    .font(.dsHeadline)
                    .foregroundStyle(.white)
            }
            .frame(height: 50)
        }
        .disabled(!viewModel.canDelete)
        .simultaneousGesture(
            LongPressGesture(minimumDuration: 3)
                .onChanged { _ in
                    guard viewModel.canDelete, !viewModel.isPressing else { return }
                    viewModel.startPressCountdown()
                }
                .onEnded { _ in
                    guard let phone = authViewModel.currentUser?.phone else { return }
                    Task {
                        let success = await viewModel.deleteAccount(phone: phone)
                        if success {
                            authViewModel.signOut()
                        }
                    }
                }
        )
        .simultaneousGesture(
            DragGesture(minimumDistance: 0)
                .onEnded { _ in
                    if viewModel.isPressing && viewModel.pressCountdown > 0 {
                        viewModel.cancelPress()
                    }
                }
        )
    }

    private func dataRow(_ text: String) -> some View {
        HStack(spacing: Spacing.sm) {
            Image(systemName: "minus.circle.fill")
                .foregroundStyle(Color.danger)
                .font(.dsCaption)
            Text(text)
                .font(.dsBody)
                .foregroundStyle(Color.textSecondary)
        }
    }
}

#Preview {
    NavigationStack {
        DeleteAccountView()
            .environmentObject(AuthViewModel())
    }
}
