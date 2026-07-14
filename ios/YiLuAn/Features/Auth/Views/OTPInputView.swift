import SwiftUI

struct OTPInputView: View {
    let phone: String
    @EnvironmentObject var authViewModel: AuthViewModel
    @EnvironmentObject var loc: LocalizationManager
    @State private var code = ""
    @FocusState private var isFocused: Bool

    var body: some View {
        VStack(spacing: 32) {
            VStack(spacing: 8) {
                Text(loc.t("login.enterCode"))
                    .font(.title2.bold())
                Text(loc.t("otp.sentTo", phone))
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            // OTP input
            TextField("000000", text: $code)
                .keyboardType(.numberPad)
                .font(.title.monospaced())
                .multilineTextAlignment(.center)
                .padding()
                .background(Color(.systemGray6))
                .cornerRadius(12)
                .focused($isFocused)
                .onChange(of: code) { _, newValue in
                    // Limit to 6 digits
                    if newValue.count > 6 {
                        code = String(newValue.prefix(6))
                    }
                    // Auto-submit when 6 digits entered
                    if newValue.count == 6 {
                        Task {
                            await authViewModel.verifyOTP(phone: phone, code: code)
                        }
                    }
                }
                .padding(.horizontal)

            if authViewModel.isLoading {
                ProgressView()
            }

            if let error = authViewModel.errorMessage {
                Text(error)
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            Spacer()
        }
        .padding(.top, 40)
        .onAppear { isFocused = true }
    }
}

#Preview {
    OTPInputView(phone: "13800138000")
        .environmentObject(AuthViewModel())
        .environmentObject(LocalizationManager.shared)
}
