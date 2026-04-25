import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @State private var phone = ""
    @State private var showOTPInput = false
    @State private var agreedToTerms = false
    @State private var appear = false

    var body: some View {
        NavigationStack {
            ZStack {
                // Gradient background
                LinearGradient(
                    colors: [Color.brand.opacity(0.08), Color.bgPage],
                    startPoint: .top, endPoint: .center
                )
                .ignoresSafeArea()

                VStack(spacing: Spacing.xxl) {
                    Spacer()

                    // Logo area
                    VStack(spacing: Spacing.md) {
                        ZStack {
                            Circle()
                                .fill(AppGradient.primary)
                                .frame(width: 88, height: 88)
                                .shadow(color: .brand.opacity(0.3), radius: 16, x: 0, y: 8)

                            Image(systemName: "cross.case.fill")
                                .font(.system(size: 36))
                                .foregroundStyle(.white)
                        }

                        Text("医路安")
                            .font(.dsHero)
                            .foregroundStyle(Color.textPrimary)

                        Text("专业陪诊，安心就医")
                            .font(.dsBody)
                            .foregroundStyle(Color.textSecondary)
                    }
                    .opacity(appear ? 1 : 0)
                    .offset(y: appear ? 0 : 20)

                    // Phone input
                    VStack(spacing: Spacing.lg) {
                        HStack(spacing: Spacing.md) {
                            Text("+86")
                                .font(.dsBody)
                                .foregroundStyle(Color.textHint)
                                .frame(width: 40)

                            TextField("请输入手机号", text: $phone)
                                .keyboardType(.phonePad)
                                .font(.dsBody)
                        }
                        .padding()
                        .background(Color.bgInput)
                        .overlay(
                            RoundedRectangle(cornerRadius: CGFloat(CornerRadius.md))
                                .stroke(Color.borderInput, lineWidth: 1)
                        )
                        .cornerRadius(CGFloat(CornerRadius.md))

                        Button {
                            Task {
                                await authViewModel.sendOTP(phone: phone)
                                if authViewModel.errorMessage == nil {
                                    showOTPInput = true
                                }
                            }
                        } label: {
                            Text("获取验证码")
                                .font(.dsTitle)
                                .fontWeight(.semibold)
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 16)
                        }
                        .buttonStyle(PrimaryButtonStyle())
                        .disabled(phone.count != 11 || authViewModel.isLoading || !agreedToTerms)
                        .opacity(phone.count != 11 || !agreedToTerms ? 0.5 : 1.0)

                        if let error = authViewModel.errorMessage {
                            HStack(spacing: 6) {
                                Image(systemName: "exclamationmark.circle")
                                    .font(.dsCaption)
                                Text(error)
                                    .font(.dsCaption)
                            }
                            .foregroundStyle(Color.danger)
                            .transition(.opacity.combined(with: .move(edge: .top)))
                        }

                        // Apple Sign-In (W18-A) — system component, follows Apple HIG.
                        SignInWithAppleButton(
                            .signIn,
                            onRequest: { request in
                                request.requestedScopes = [.fullName, .email]
                            },
                            onCompletion: { _ in
                                // Delegate-based path is unused here; we drive the
                                // flow through AppleSignInService for testability.
                                Task {
                                    guard agreedToTerms else { return }
                                    await authViewModel.loginWithApple()
                                }
                            }
                        )
                        .signInWithAppleButtonStyle(.black)
                        .frame(height: 48)
                        .cornerRadius(CGFloat(CornerRadius.md))
                        .disabled(!agreedToTerms || authViewModel.isLoading)
                        .opacity(agreedToTerms ? 1.0 : 0.5)
                    }
                    .padding(.horizontal, Spacing.xl)
                    .opacity(appear ? 1 : 0)
                    .offset(y: appear ? 0 : 20)

                    Spacer()

                    // Privacy agreement
                    VStack(spacing: Spacing.sm) {
                        HStack(alignment: .top, spacing: Spacing.sm) {
                            Button {
                                withAnimation(.spring(response: 0.3)) {
                                    agreedToTerms.toggle()
                                }
                            } label: {
                                Image(systemName: agreedToTerms ? "checkmark.circle.fill" : "circle")
                                    .font(.system(size: 20))
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
                    .padding(.horizontal, Spacing.xl)
                    .padding(.bottom, Spacing.xxl)
                    .opacity(appear ? 1 : 0)
                }
            }
            .navigationTitle("")
            .navigationDestination(isPresented: $showOTPInput) {
                OTPInputView(phone: phone)
                    .environmentObject(authViewModel)
            }
            .onAppear {
                withAnimation(.easeOut(duration: 0.6)) {
                    appear = true
                }
            }
        }
    }
}

#Preview {
    LoginView()
        .environmentObject(AuthViewModel())
}
