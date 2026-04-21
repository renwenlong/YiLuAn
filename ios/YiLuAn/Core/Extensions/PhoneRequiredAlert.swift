import SwiftUI

/// 在 View 上挂一个全局 PHONE_REQUIRED 处理：弹 alert，点「去绑定」后 push BindPhoneView；
/// 取消则直接关闭。使用：`.phoneRequiredAlert($viewModel.phoneRequiredMessage)`。
struct PhoneRequiredAlertModifier: ViewModifier {
    @Binding var message: String?
    @State private var showBindPhone = false

    func body(content: Content) -> some View {
        content
            .alert(
                "请先绑定手机号",
                isPresented: Binding(
                    get: { message != nil },
                    set: { if !$0 { message = nil } }
                ),
                presenting: message
            ) { _ in
                Button("去绑定") {
                    message = nil
                    showBindPhone = true
                }
                Button("取消", role: .cancel) {
                    message = nil
                }
            } message: { msg in
                Text(msg)
            }
            .sheet(isPresented: $showBindPhone) {
                NavigationStack {
                    BindPhoneView()
                }
            }
    }
}

extension View {
    /// 当 message 非 nil 时弹出「请先绑定手机号」alert，点「去绑定」push BindPhoneView。
    func phoneRequiredAlert(_ message: Binding<String?>) -> some View {
        modifier(PhoneRequiredAlertModifier(message: message))
    }

    /// 当 message 非 nil 时弹出「请先完成支付」alert。
    func paymentRequiredAlert(_ message: Binding<String?>) -> some View {
        modifier(PaymentRequiredAlertModifier(message: message))
    }

    /// 当 message 非 nil 时弹出「资质未审核」alert。
    func verificationRequiredAlert(_ message: Binding<String?>) -> some View {
        modifier(VerificationRequiredAlertModifier(message: message))
    }
}

/// 弹出 PAYMENT_REQUIRED 提示：默认只有确认按钮，关闭后清理 message。
struct PaymentRequiredAlertModifier: ViewModifier {
    @Binding var message: String?

    func body(content: Content) -> some View {
        content.alert(
            "订单尚未支付",
            isPresented: Binding(
                get: { message != nil },
                set: { if !$0 { message = nil } }
            ),
            presenting: message
        ) { _ in
            Button("知道了", role: .cancel) { message = nil }
        } message: { msg in
            Text(msg)
        }
    }
}

/// 弹出 VERIFICATION_REQUIRED 提示：默认只有确认按钮，关闭后清理 message。
struct VerificationRequiredAlertModifier: ViewModifier {
    @Binding var message: String?

    func body(content: Content) -> some View {
        content.alert(
            "资质审核中",
            isPresented: Binding(
                get: { message != nil },
                set: { if !$0 { message = nil } }
            ),
            presenting: message
        ) { _ in
            Button("知道了", role: .cancel) { message = nil }
        } message: { msg in
            Text(msg)
        }
    }
}
