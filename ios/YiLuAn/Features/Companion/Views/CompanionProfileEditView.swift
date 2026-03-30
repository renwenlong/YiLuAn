import SwiftUI

struct CompanionProfileEditView: View {
    @StateObject private var viewModel = CompanionProfileViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Form {
            // Verification status
            if let companion = viewModel.selectedCompanion {
                Section("认证状态") {
                    HStack {
                        Text("状态")
                        Spacer()
                        verificationBadge(companion.verificationStatus)
                    }
                    if let realName = viewModel.selectedCompanion?.realName {
                        HStack {
                            Text("实名")
                            Spacer()
                            Text(realName)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            Section("服务信息") {
                VStack(alignment: .leading) {
                    Text("个人简介")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextEditor(text: $viewModel.bio)
                        .frame(minHeight: 120)
                }

                TextField("服务区域", text: $viewModel.serviceArea)
            }

            Section {
                Button(action: {
                    Task { await viewModel.updateProfile() }
                }) {
                    HStack {
                        Spacer()
                        if viewModel.isLoading {
                            ProgressView()
                        } else {
                            Text("保存")
                        }
                        Spacer()
                    }
                }
                .disabled(viewModel.isLoading)
            }
        }
        .navigationTitle("陪诊师信息")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadOwnProfile()
        }
        .onChange(of: viewModel.isSaved) { saved in
            if saved { dismiss() }
        }
        .alert("错误", isPresented: .init(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button("确定", role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    @ViewBuilder
    private func verificationBadge(_ status: String) -> some View {
        switch status {
        case "verified":
            Label("已认证", systemImage: "checkmark.seal.fill")
                .font(.caption)
                .foregroundStyle(.green)
        case "pending":
            Label("审核中", systemImage: "clock.fill")
                .font(.caption)
                .foregroundStyle(.orange)
        case "rejected":
            Label("未通过", systemImage: "xmark.seal.fill")
                .font(.caption)
                .foregroundStyle(.red)
        default:
            Label("未认证", systemImage: "questionmark.circle")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

#Preview {
    NavigationStack {
        CompanionProfileEditView()
    }
}
