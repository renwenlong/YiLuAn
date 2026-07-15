import SwiftUI

struct PatientProfileEditView: View {
    @StateObject private var viewModel = PatientProfileViewModel()
    @EnvironmentObject var loc: LocalizationManager
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Form {
            Section(loc.t("profileEdit.emergencyContact")) {
                TextField(loc.t("patientProfile.contactName"), text: $viewModel.emergencyContact)
                TextField(loc.t("patientProfile.contactPhone"), text: $viewModel.emergencyPhone)
                    .keyboardType(.phonePad)
            }

            Section(loc.t("patientProfile.medicalInfo")) {
                VStack(alignment: .leading) {
                    Text(loc.t("patientProfile.medicalNotes"))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextEditor(text: $viewModel.medicalNotes)
                        .frame(minHeight: 120)
                }
            }

            if !viewModel.hospitals.isEmpty {
                Section(loc.t("patientProfile.preferredHospital")) {
                    Picker(loc.t("patientProfile.selectHospital"), selection: $viewModel.preferredHospitalId) {
                        Text(loc.t("patientProfile.notSelected")).tag("")
                        ForEach(viewModel.hospitals) { hospital in
                            Text(hospital.name).tag(hospital.id)
                        }
                    }
                }
            }

            Section {
                Button(action: {
                    Task { await viewModel.saveProfile() }
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
        .navigationTitle(loc.t("patientProfile.title"))
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadProfile()
            await viewModel.loadHospitals()
        }
        .onChange(of: viewModel.isSaved) { saved in
            if saved { dismiss() }
        }
        .alert(loc.t("patientProfile.errorTitle"), isPresented: .init(
            get: { viewModel.errorMessage != nil },
            set: { if !$0 { viewModel.errorMessage = nil } }
        )) {
            Button(loc.t("patientProfile.ok"), role: .cancel) {}
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
    }
}

#Preview {
    NavigationStack {
        PatientProfileEditView()
    }
}
