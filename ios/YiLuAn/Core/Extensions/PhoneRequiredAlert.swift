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
}
