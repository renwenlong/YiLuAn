import SwiftUI

struct BindPhoneView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @EnvironmentObject var loc: LocalizationManager
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
            Section(loc.t("login.phone")) {
                HStack {
                    Text("+86")
                        .foregroundStyle(.secondary)
                    TextField(loc.t("login.inputPhone"), text: $phone)
                        .keyboardType(.phonePad)
                }
            }

            Section(loc.t("login.codeLabel")) {
                HStack {
                    TextField(loc.t("login.inputCode"), text: $otpCode)
                        .keyboardType(.numberPad)

                    Button {
                        Task { await sendOTP() }
                    } label: {
                        Text(otpCountdown > 0 ? "\(otpCountdown)s" : loc.t("login.getCode"))
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
                            Text(loc.t("bindPhone.bindPhone"))
                        }
                        Spacer()
                    }
                }
                .disabled(phone.count != 11 || otpCode.count != 6 || isBinding)
            }
        }
        .navigationTitle(loc.t("bindPhone.bindPhone"))
        .navigationBarTitleDisplayMode(.inline)
        .alert(loc.t("bindPhone.bindSuccess"), isPresented: $showSuccess) {
            Button(loc.t("companion.ok")) { dismiss() }
        } message: {
            Text(loc.t("bindPhone.phoneBoundSuccess"))
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
