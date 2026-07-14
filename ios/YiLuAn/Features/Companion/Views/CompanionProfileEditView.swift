import SwiftUI

struct CompanionProfileEditView: View {
    @EnvironmentObject var loc: LocalizationManager
    @StateObject private var viewModel = CompanionProfileViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Form {
            // Verification status
            if let companion = viewModel.selectedCompanion {
                Section(loc.t("companion.verificationStatus")) {
                    HStack {
                        Text(loc.t("companion.status"))
                        Spacer()
                        verificationBadge(companion.verificationStatus)
                    }
                    if let realName = viewModel.selectedCompanion?.realName {
                        HStack {
                            Text(loc.t("companion.realName"))
                            Spacer()
                            Text(realName)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            Section(loc.t("companionDetail.serviceInfo")) {
                VStack(alignment: .leading) {
                    Text(loc.t("profileEdit.bio"))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextEditor(text: $viewModel.bio)
                        .frame(minHeight: 120)
                }

                TextField(loc.t("profileEdit.serviceArea"), text: $viewModel.serviceArea)
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
                            Text(loc.t("common.save"))
                        }
                        Spacer()
                    }
                }
                .disabled(viewModel.isLoading)
            }
        }
        .navigationTitle(loc.t("orderDetail.companionInfo"))
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadOwnProfile()
        }
        .onChange(of: viewModel.isSaved) { saved in
            if saved { dismiss() }
        }
        .alert(loc.t("companion.error"), isPresented: .init(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button(loc.t("companion.ok"), role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }

    @ViewBuilder
    private func verificationBadge(_ status: String) -> some View {
        switch status {
        case "verified":
            Label(loc.t("createOrder.verified"), systemImage: "checkmark.seal.fill")
                .font(.caption)
                .foregroundStyle(.green)
        case "pending":
            Label(loc.t("companion.underReview"), systemImage: "clock.fill")
                .font(.caption)
                .foregroundStyle(.orange)
        case "rejected":
            Label(loc.t("companion.notApproved"), systemImage: "xmark.seal.fill")
                .font(.caption)
                .foregroundStyle(.red)
        default:
            Label(loc.t("companionDetail.unverified"), systemImage: "questionmark.circle")
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
