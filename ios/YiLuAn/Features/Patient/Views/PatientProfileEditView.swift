import SwiftUI

struct PatientProfileEditView: View {
    @StateObject private var viewModel = PatientProfileViewModel()
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Form {
            Section("紧急联系人") {
                TextField("联系人姓名", text: $viewModel.emergencyContact)
                TextField("联系人电话", text: $viewModel.emergencyPhone)
                    .keyboardType(.phonePad)
            }

            Section("医疗信息") {
                VStack(alignment: .leading) {
                    Text("病历备注")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    TextEditor(text: $viewModel.medicalNotes)
                        .frame(minHeight: 120)
                }
            }

            if !viewModel.hospitals.isEmpty {
                Section("偏好医院") {
                    Picker("选择医院", selection: $viewModel.preferredHospitalId) {
                        Text("未选择").tag("")
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
                            Text("保存")
                        }
                        Spacer()
                    }
                }
                .disabled(viewModel.isLoading)
            }
        }
        .navigationTitle("患者信息")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadProfile()
            await viewModel.loadHospitals()
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
}

#Preview {
    NavigationStack {
        PatientProfileEditView()
    }
}
