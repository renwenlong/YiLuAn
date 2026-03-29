import SwiftUI

struct LoginView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @State private var phone = ""
    @State private var showOTPInput = false

    var body: some View {
        NavigationStack {
            VStack(spacing: 32) {
                Spacer()

                // Logo area
                VStack(spacing: 12) {
                    Image(systemName: "cross.case.fill")
                        .font(.system(size: 64))
                        .foregroundStyle(.blue)
                    Text("医路安")
                        .font(.largeTitle.bold())
                    Text("专业陪诊，安心就医")
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                // Phone input
                VStack(spacing: 16) {
                    HStack {
                        Text("+86")
                            .foregroundStyle(.secondary)
                        TextField("请输入手机号", text: $phone)
                            .keyboardType(.phonePad)
                    }
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(12)

                    Button {
                        Task {
                            await authViewModel.sendOTP(phone: phone)
                            if authViewModel.errorMessage == nil {
                                showOTPInput = true
                            }
                        }
                    } label: {
                        Text("获取验证码")
                            .frame(maxWidth: .infinity)
                            .padding()
                            .background(phone.count == 11 ? Color.blue : Color.gray)
                            .foregroundStyle(.white)
                            .cornerRadius(12)
                    }
                    .disabled(phone.count != 11 || authViewModel.isLoading)

                    if let error = authViewModel.errorMessage {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
                .padding(.horizontal)

                Spacer()
                Spacer()
            }
            .navigationTitle("")
            .navigationDestination(isPresented: $showOTPInput) {
                OTPInputView(phone: phone)
                    .environmentObject(authViewModel)
            }
        }
    }
}

#Preview {
    LoginView()
        .environmentObject(AuthViewModel())
}
