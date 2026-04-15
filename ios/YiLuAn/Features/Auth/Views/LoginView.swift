import SwiftUI

struct LoginView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @State private var phone = ""
    @State private var showOTPInput = false
    @State private var agreedToTerms = false

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
                            .background(phone.count == 11 && agreedToTerms ? Color.blue : Color.gray)
                            .foregroundStyle(.white)
                            .cornerRadius(12)
                    }
                    .disabled(phone.count != 11 || authViewModel.isLoading || !agreedToTerms)

                    if let error = authViewModel.errorMessage {
                        Text(error)
                            .font(.caption)
                            .foregroundStyle(.red)
                    }
                }
                .padding(.horizontal)

                Spacer()

                // Privacy agreement
                VStack(spacing: 8) {
                    HStack(alignment: .top, spacing: 8) {
                        Button {
                            agreedToTerms.toggle()
                        } label: {
                            Image(systemName: agreedToTerms ? "checkmark.circle.fill" : "circle")
                                .foregroundStyle(agreedToTerms ? Color.brand : Color.textHint)
                        }

                        Text("我已阅读并同意")
                            .font(.dsCaption)
                            .foregroundStyle(Color.textSecondary)
                        +
                        Text("《用户协议》")
                            .font(.dsCaption)
                            .foregroundStyle(Color.brand)
                        +
                        Text("和")
                            .font(.dsCaption)
                            .foregroundStyle(Color.textSecondary)
                        +
                        Text("《隐私政策》")
                            .font(.dsCaption)
                            .foregroundStyle(Color.brand)
                    }
                }
                .padding(.horizontal)
                .padding(.bottom, 32)
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
