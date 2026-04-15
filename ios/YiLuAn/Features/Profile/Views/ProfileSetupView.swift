import SwiftUI

struct ProfileSetupView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @State private var displayName = ""
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: Spacing.xxl) {
            Spacer()

            Image(systemName: "person.crop.circle.badge.plus")
                .font(.system(size: 72))
                .foregroundStyle(Color.brand)

            Text("设置个人资料")
                .font(.title2.bold())

            Text("请设置您的昵称以完成注册")
                .font(.dsSubheadline)
                .foregroundStyle(.secondary)

            VStack(spacing: Spacing.lg) {
                TextField("请输入昵称", text: $displayName)
                    .padding()
                    .background(Color(.systemGray6))
                    .cornerRadius(CornerRadius.lg)
                    .padding(.horizontal)

                if let errorMessage {
                    Text(errorMessage)
                        .font(.dsCaption)
                        .foregroundStyle(.red)
                }

                Button {
                    Task { await saveProfile() }
                } label: {
                    HStack {
                        if isLoading {
                            ProgressView()
                                .tint(.white)
                        }
                        Text("完成设置")
                    }
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(displayName.trimmingCharacters(in: .whitespaces).isEmpty ? Color.gray : Color.brand)
                    .foregroundStyle(.white)
                    .cornerRadius(CornerRadius.lg)
                }
                .disabled(displayName.trimmingCharacters(in: .whitespaces).isEmpty || isLoading)
                .padding(.horizontal)
            }

            Spacer()
            Spacer()
        }
    }

    private func saveProfile() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let body = UpdateDisplayNameRequest(displayName: displayName.trimmingCharacters(in: .whitespaces))
            let user: User = try await APIClient.shared.request(.updateMe, body: body)
            authViewModel.currentUser = user
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

#Preview {
    ProfileSetupView()
        .environmentObject(AuthViewModel())
}
