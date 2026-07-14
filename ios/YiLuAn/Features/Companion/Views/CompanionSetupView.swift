import SwiftUI

struct CompanionSetupView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = CompanionProfileViewModel()
    @EnvironmentObject var loc: LocalizationManager

    @State private var realName = ""
    @State private var idNumber = ""
    @State private var selectedServiceTypes: Set<ServiceType> = []
    @State private var serviceArea = ""
    @State private var bio = ""
    @State private var isSubmitting = false
    @State private var errorMessage: String?
    @State private var showSuccess = false

    var body: some View {
        Form {
            Section(loc.t("companion.basicInfo")) {
                TextField(loc.t("companion.realNameRequired"), text: $realName)
                TextField(loc.t("companion.idNumberOptional"), text: $idNumber)
                    .keyboardType(.asciiCapable)
            }

            Section(loc.t("companion.serviceTypeMin")) {
                ForEach(ServiceType.allCases, id: \.self) { type in
                    Button {
                        if selectedServiceTypes.contains(type) {
                            selectedServiceTypes.remove(type)
                        } else {
                            selectedServiceTypes.insert(type)
                        }
                    } label: {
                        HStack {
                            Text(type.displayName)
                                .foregroundStyle(Color.textPrimary)
                            Spacer()
                            Text("¥\(type.price)")
                                .foregroundStyle(Color.textSecondary)
                            if selectedServiceTypes.contains(type) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundStyle(Color.brand)
                            } else {
                                Image(systemName: "circle")
                                    .foregroundStyle(Color.textHint)
                            }
                        }
                    }
                }
            }

            Section(loc.t("profileEdit.serviceArea")) {
                TextField(loc.t("companion.districtExample"), text: $serviceArea)
            }

            Section(loc.t("profileEdit.bio")) {
                TextEditor(text: $bio)
                    .frame(minHeight: 80)
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
                    Task { await submitApplication() }
                } label: {
                    HStack {
                        Spacer()
                        if isSubmitting {
                            ProgressView()
                        } else {
                            Text(loc.t("companion.submitApplication"))
                                .bold()
                        }
                        Spacer()
                    }
                }
                .disabled(!canSubmit || isSubmitting)
            }
        }
        .navigationTitle(loc.t("companion.onboarding"))
        .navigationBarTitleDisplayMode(.inline)
        .phoneRequiredAlert($viewModel.phoneRequiredMessage)
        .alert(loc.t("companion.applicationSubmitted"), isPresented: $showSuccess) {
            Button(loc.t("companion.ok")) { dismiss() }
        } message: {
            Text(loc.t("companion.onboardingSubmitted"))
        }
    }

    private var canSubmit: Bool {
        !realName.trimmingCharacters(in: .whitespaces).isEmpty && !selectedServiceTypes.isEmpty
    }

    private func submitApplication() async {
        isSubmitting = true
        errorMessage = nil
        defer { isSubmitting = false }

        await viewModel.applyAsCompanion(
            realName: realName.trimmingCharacters(in: .whitespaces),
            idNumber: idNumber.isEmpty ? nil : idNumber,
            serviceArea: serviceArea.isEmpty ? nil : serviceArea,
            bio: bio.isEmpty ? nil : bio
        )

        if viewModel.errorMessage == nil {
            await authViewModel.fetchCurrentUser()
            showSuccess = true
        } else {
            errorMessage = viewModel.errorMessage
        }
    }
}

#Preview {
    NavigationStack {
        CompanionSetupView()
            .environmentObject(AuthViewModel())
    }
}
