import SwiftUI

struct DeleteAccountView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @StateObject private var viewModel = SettingsViewModel()
    @State private var showResult = false

    var body: some View {
        ScrollView {
            VStack(spacing: Spacing.xl) {
                // Warning header
                VStack(spacing: Spacing.sm) {
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 48))
                        .foregroundStyle(Color.warning)
                    Text("注销账号")
                        .font(.title2.bold())
                    Text("此操作不可恢复，请谨慎操作")
                        .font(.dsSubheadline)
                        .foregroundStyle(Color.textHint)
                }
                .padding(.top, Spacing.xl)

                // Data card
                VStack(alignment: .leading, spacing: Spacing.md) {
                    Text("注销后以下数据将被删除：")
                        .font(.dsHeadline)
                    dataRow("订单记录和交易数据")
                    dataRow("个人资料和认证信息")
                    dataRow("钱包余额和支付信息")
                    dataRow("聊天记录")
                    dataRow("陪诊师认证资料")
                }
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(CornerRadius.lg)

                // Recovery notice
                HStack {
                    Image(systemName: "info.circle.fill")
                        .foregroundStyle(Color.warning)
                    Text("注销后 30 天内可联系客服恢复账号")
                        .font(.dsSubheadline)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.warning.opacity(0.1))
                .cornerRadius(CornerRadius.md)

                // OTP verification
                VStack(alignment: .leading, spacing: Spacing.md) {
                    Text("验证身份")
                        .font(.dsHeadline)

                    HStack {
                        TextField("输入6位验证码", text: $viewModel.otpCode)
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
                            Text(viewModel.otpCountdown > 0 ? "\(viewModel.otpCountdown)s" : "发送验证码")
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
                        Text("我已阅读并理解注销账号的后果，确认注销")
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
        .navigationTitle("注销账号")
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

                Text(viewModel.isPressing ? "继续按住 \(viewModel.pressCountdown)s" : "长按 3 秒确认注销")
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
