import SwiftUI

struct CompanionSetupView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = CompanionProfileViewModel()

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
            Section("基本信息") {
                TextField("真实姓名（必填）", text: $realName)
                TextField("身份证号（选填）", text: $idNumber)
                    .keyboardType(.asciiCapable)
            }

            Section("服务类型（至少选一项）") {
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

            Section("服务区域") {
                TextField("例如：朝阳区、东城区", text: $serviceArea)
            }

            Section("个人简介") {
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
                            Text("提交申请")
                                .bold()
                        }
                        Spacer()
                    }
                }
                .disabled(!canSubmit || isSubmitting)
            }
        }
        .navigationTitle("陪诊师入驻")
        .navigationBarTitleDisplayMode(.inline)
        .alert("申请已提交", isPresented: $showSuccess) {
            Button("确定") { dismiss() }
        } message: {
            Text("您的陪诊师入驻申请已提交，审核通过后即可开始接单。")
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
