import SwiftUI

struct BindPhoneView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @Environment(\.dismiss) private var dismiss
    @State private var phone = ""
    @State private var otpCode = ""
    @State private var otpCountdown = 0
    @State private var isSendingOTP = false
    @State private var isBinding = false
    @State private var errorMessage: String?
    @State private var showSuccess = false

    private var otpTimer: Timer? = nil

    var body: some View {
        Form {
            Section("手机号") {
                HStack {
                    Text("+86")
                        .foregroundStyle(.secondary)
                    TextField("请输入手机号", text: $phone)
                        .keyboardType(.phonePad)
                }
            }

            Section("验证码") {
                HStack {
                    TextField("请输入6位验证码", text: $otpCode)
                        .keyboardType(.numberPad)

                    Button {
                        Task { await sendOTP() }
                    } label: {
                        Text(otpCountdown > 0 ? "\(otpCountdown)s" : "获取验证码")
                            .font(.dsSubheadline)
                    }
                    .disabled(phone.count != 11 || otpCountdown > 0 || isSendingOTP)
                }
            }

            if let errorMessage {
                Section {
                    Text(errorMessage)
                        .foregroundStyle(.red)
                        .font(.dsCaption)
                }
            }

            Section {
                Button {
                    Task { await bindPhone() }
                } label: {
                    HStack {
                        Spacer()
                        if isBinding {
                            ProgressView()
                        } else {
                            Text("绑定手机号")
                        }
                        Spacer()
                    }
                }
                .disabled(phone.count != 11 || otpCode.count != 6 || isBinding)
            }
        }
        .navigationTitle("绑定手机号")
        .navigationBarTitleDisplayMode(.inline)
        .alert("绑定成功", isPresented: $showSuccess) {
            Button("确定") { dismiss() }
        } message: {
            Text("手机号已成功绑定")
        }
    }

    private func sendOTP() async {
        isSendingOTP = true
        errorMessage = nil
        defer { isSendingOTP = false }

        do {
            let request = SendOTPRequest(phone: phone)
            try await APIClient.shared.requestVoid(.sendOTP, body: request)
            startCountdown()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func bindPhone() async {
        isBinding = true
        errorMessage = nil
        defer { isBinding = false }

        do {
            let body = BindPhoneRequest(phone: phone, code: otpCode)
            try await APIClient.shared.requestVoid(.bindPhone, body: body)
            await authViewModel.fetchCurrentUser()
            showSuccess = true
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func startCountdown() {
        otpCountdown = 60
        Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { timer in
            Task { @MainActor in
                otpCountdown -= 1
                if otpCountdown <= 0 {
                    timer.invalidate()
                    otpCountdown = 0
                }
            }
        }
    }
}

#Preview {
    NavigationStack {
        BindPhoneView()
            .environmentObject(AuthViewModel())
    }
}
