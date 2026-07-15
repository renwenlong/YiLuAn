import SwiftUI

/// 家属端 share OTP 输入页（S2-INT-004 / F2 OTP UI）
///
/// 入口：UniversalLink `https://m.yiluan.cn/s/{token}` 截获 → 直接构造本 view
/// 流程：手机号 → sendOTP → 6 位 OTP → exchangeSession → success 跳 ShareOrderView
///
/// 与微信端 wx_openid 静默授权对立：
///   - 微信端：jscode2session 自动拿 openid，零交互
///   - iOS 端 / 外部浏览器：必须手输手机号 + OTP（短信 fallback）
struct ShareOTPView: View {
    @EnvironmentObject var loc: LocalizationManager
    @StateObject private var viewModel: ShareOTPViewModel
    @Environment(\.dismiss) private var dismiss

    /// success 后通知外层跳 ShareOrderView（外层提供 orderId / scope 路由）
    var onAuthenticated: ((UUID, ShareScope) -> Void)?

    /// 是否在 success 后直接 push ShareOrderView（默认 true）
    /// 外层可设 false 自行控制路由
    let pushShareOrderViewOnSuccess: Bool

    @State private var navigateToOrderView: Bool = false

    init(
        shareToken: String,
        pushShareOrderViewOnSuccess: Bool = true,
        onAuthenticated: ((UUID, ShareScope) -> Void)? = nil
    ) {
        _viewModel = StateObject(wrappedValue: ShareOTPViewModel(shareToken: shareToken))
        self.pushShareOrderViewOnSuccess = pushShareOrderViewOnSuccess
        self.onAuthenticated = onAuthenticated
    }

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 24) {
                header
                Group {
                    switch viewModel.stage {
                    case .enterPhone:
                        phoneInput
                    case .sendingOTP:
                        loadingView(text: loc.t("share.sendingOtp"))
                    case .enterOTP(let masked, let expiresIn):
                        otpInput(maskedPhone: masked, expiresIn: expiresIn)
                    case .exchanging:
                        loadingView(text: loc.t("share.verifying"))
                    case .success(let s):
                        successView(orderId: s.orderId, scope: s.scope)
                    case .failure(let msg):
                        failureView(message: msg)
                    }
                }
                Spacer()
            }
            .padding()
            .navigationTitle(loc.t("share.title"))
            .navigationBarTitleDisplayMode(.inline)
            .navigationDestination(isPresented: $navigateToOrderView) {
                if let active = ShareSessionStore.activeSession() {
                    ShareOrderView(shareSession: active)
                }
            }
        }
    }

    // MARK: - Sections

    private var header: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(loc.t("share.viewProgress"))
                .font(.title2.weight(.semibold))
            Text(loc.t("share.privacyHint"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private var phoneInput: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(loc.t("share.phoneLabel"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
            TextField(loc.t("share.phonePlaceholder"), text: $viewModel.phone)
                .textFieldStyle(.roundedBorder)
                .keyboardType(.numberPad)
                .textContentType(.telephoneNumber)
                .font(.body)

            Button {
                Task { await viewModel.sendOTP() }
            } label: {
                Text(loc.t("share.getOtp"))
                    .font(.body.weight(.semibold))
                    .frame(maxWidth: .infinity)
                    .frame(height: 48)
                    .background(viewModel.phone.isEmpty ? Color(.systemGray3) : Color.blue)
                    .foregroundStyle(.white)
                    .cornerRadius(12)
            }
            .disabled(viewModel.phone.isEmpty)
        }
    }

    private func otpInput(maskedPhone: String, expiresIn: Int) -> some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text(loc.t("share.otpSentTo"))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                Text(maskedPhone)
                    .font(.body.weight(.semibold))
                if expiresIn > 0 {
                    Text(loc.t("share.validForMinutes", "\(expiresIn / 60)"))
                        .font(.caption)
                        .foregroundStyle(.tertiary)
                }
            }

            Text(loc.t("share.otpLabel"))
                .font(.subheadline)
                .foregroundStyle(.secondary)
            TextField(loc.t("share.otpPlaceholder"), text: $viewModel.otp)
                .textFieldStyle(.roundedBorder)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .font(.body)

            HStack {
                Button(loc.t("share.reenterPhone")) {
                    viewModel.resetToEnterPhone()
                }
                .font(.subheadline)
                Spacer()
                Button {
                    Task { await viewModel.exchangeSession() }
                } label: {
                    Text(loc.t("share.verify"))
                        .font(.body.weight(.semibold))
                        .padding(.horizontal, 32)
                        .frame(height: 44)
                        .background(viewModel.otp.count != 6 ? Color(.systemGray3) : Color.blue)
                        .foregroundStyle(.white)
                        .cornerRadius(10)
                }
                .disabled(viewModel.otp.count != 6)
            }
        }
    }

    private func loadingView(text: String) -> some View {
        HStack {
            ProgressView()
            Text(text).foregroundStyle(.secondary).font(.subheadline)
        }
    }

    private func successView(orderId: UUID, scope: ShareScope) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "checkmark.circle.fill").foregroundStyle(.green)
                Text(loc.t("share.verifySuccess")).font(.body.weight(.semibold))
            }
            Text(loc.t("share.redirecting", scope.displayName))
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
        .onAppear {
            // 触发外层路由回调
            onAuthenticated?(orderId, scope)
            // 默认 push ShareOrderView（INT-006 购机回调）
            if pushShareOrderViewOnSuccess {
                navigateToOrderView = true
            }
        }
    }

    private func failureView(message: String) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.orange)
                Text(message).font(.subheadline)
            }
            Button(loc.t("share.retry")) {
                viewModel.resetToEnterOTP()
            }
            .buttonStyle(.bordered)
        }
    }
}
