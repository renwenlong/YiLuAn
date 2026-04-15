import SwiftUI

enum PaymentStatus: String {
    case success
    case fail
    case cancel

    var icon: String {
        switch self {
        case .success: return "checkmark.circle.fill"
        case .fail: return "xmark.circle.fill"
        case .cancel: return "exclamationmark.circle.fill"
        }
    }

    var iconColor: Color {
        switch self {
        case .success: return .success
        case .fail: return .danger
        case .cancel: return .warning
        }
    }

    var title: String {
        switch self {
        case .success: return "支付成功"
        case .fail: return "支付失败"
        case .cancel: return "支付取消"
        }
    }

    var defaultDescription: String {
        switch self {
        case .success: return "您的订单已支付，请等待陪诊师接单"
        case .fail: return "支付遇到问题，请重试"
        case .cancel: return "您已取消支付，订单尚未完成"
        }
    }
}

struct PaymentResultView: View {
    let status: PaymentStatus
    let orderId: String?
    let errorMessage: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: Spacing.xl) {
            Spacer()

            // Icon
            Image(systemName: status.icon)
                .font(.system(size: 80))
                .foregroundStyle(status.iconColor)

            // Title
            Text(status.title)
                .font(.title.bold())
                .foregroundStyle(Color.textPrimary)

            // Description
            Text(errorMessage ?? status.defaultDescription)
                .font(.dsBody)
                .foregroundStyle(Color.textHint)
                .multilineTextAlignment(.center)
                .padding(.horizontal, Spacing.xxl)

            Spacer()

            // Buttons
            VStack(spacing: Spacing.md) {
                switch status {
                case .success:
                    if orderId != nil {
                        primaryButton("查看订单") { dismiss() }
                    }
                    secondaryButton("返回首页") { dismiss() }

                case .fail, .cancel:
                    primaryButton("重新支付") { dismiss() }
                    secondaryButton(status == .fail ? "查看订单" : "返回订单") { dismiss() }
                }
            }
            .padding(.horizontal, Spacing.xxl)
            .padding(.bottom, Spacing.xxl)
        }
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button { dismiss() } label: {
                    Image(systemName: "xmark")
                        .foregroundStyle(Color.textSecondary)
                }
            }
        }
    }

    private func primaryButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.dsHeadline)
                .foregroundStyle(.white)
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .background(Color.brand)
                .cornerRadius(CornerRadius.lg)
        }
    }

    private func secondaryButton(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title)
                .font(.dsHeadline)
                .foregroundStyle(Color.textSecondary)
                .frame(maxWidth: .infinity)
                .frame(height: 48)
                .background(Color(.systemGray6))
                .cornerRadius(CornerRadius.lg)
        }
    }
}

#Preview("Success") {
    NavigationStack {
        PaymentResultView(status: .success, orderId: "123", errorMessage: nil)
    }
}

#Preview("Fail") {
    NavigationStack {
        PaymentResultView(status: .fail, orderId: "123", errorMessage: "余额不足")
    }
}

#Preview("Cancel") {
    NavigationStack {
        PaymentResultView(status: .cancel, orderId: "123", errorMessage: nil)
    }
}
