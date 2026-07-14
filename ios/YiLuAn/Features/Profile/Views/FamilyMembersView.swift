import SwiftUI

/// F-05: 家人 / 实际就诊人列表与新增（最小 MVP）。
/// 下单页 picker 与详情展示在后续 iOS 迭代中补全（追踪：TD-IOS-FAMILY-PICKER）。
struct FamilyMembersView: View {
    @StateObject private var viewModel = FamilyMembersViewModel()
    @EnvironmentObject var loc: LocalizationManager
    @State private var showingCreate = false

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.members.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if viewModel.members.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "person.2.fill")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text(loc.t("familyMembers.empty"))
                        .foregroundColor(.secondary)
                    Text(loc.t("familyMembers.addToBookForFamily"))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(viewModel.members) { member in
                        VStack(alignment: .leading, spacing: 4) {
                            HStack {
                                Text(member.name).font(.headline)
                                Text("·").foregroundColor(.secondary)
                                Text(member.relationLabel)
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                            }
                            if let phone = member.phone, !phone.isEmpty {
                                Text(phone)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                            if let notes = member.medicalNotes, !notes.isEmpty {
                                Text(notes)
                                    .font(.caption)
                                    .foregroundColor(.orange)
                                    .lineLimit(2)
                            }
                        }
                        .padding(.vertical, 4)
                    }
                    .onDelete { offsets in
                        Task {
                            for index in offsets {
                                await viewModel.delete(viewModel.members[index])
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(loc.t("profile.menuFamily"))
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button { showingCreate = true } label: {
                    Image(systemName: "plus")
                }
            }
        }
        .sheet(isPresented: $showingCreate) {
            FamilyMemberCreateSheet { name, relation, phone, gender, age, notes in
                let ok = await viewModel.create(
                    name: name, relation: relation, phone: phone,
                    gender: gender, age: age, notes: notes
                )
                if ok { showingCreate = false }
            }
        }
        .alert(loc.t("dialog.tip"), isPresented: .constant(viewModel.errorMessage != nil)) {
            Button(loc.t("order.ok")) { viewModel.errorMessage = nil }
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
        .task { await viewModel.load() }
    }
}

private struct FamilyMemberCreateSheet: View {
    let onSave: (_ name: String, _ relation: String, _ phone: String?,
                 _ gender: String, _ age: Int?, _ notes: String?) async -> Void

    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject var loc: LocalizationManager
    @State private var name = ""
    @State private var relation = "parent"
    @State private var phone = ""
    @State private var gender = "unknown"
    @State private var ageText = ""
    @State private var notes = ""
    @State private var submitting = false

    // 复用 FamilyRelation.allCases(Model 层 computed, label 已走 loc 字典) —— 不重复定义硬编码中文

    var body: some View {
        NavigationView {
            Form {
                Section(loc.t("companion.basicInfo")) {
                    TextField(loc.t("orderDetail.nameLabel"), text: $name)
                    Picker(loc.t("emergencyContacts.relationLabel"), selection: $relation) {
                        ForEach(FamilyRelation.allCases, id: \.value) { Text($0.label).tag($0.value) }
                    }
                    Picker(loc.t("familyMembers.genderLabel"), selection: $gender) {
                        Text(loc.t("familyMembers.notFilled")).tag("unknown")
                        Text(loc.t("familyMembers.genderMale")).tag("male")
                        Text(loc.t("familyMembers.genderFemale")).tag("female")
                    }
                    TextField(loc.t("familyMembers.ageOptional"), text: $ageText)
                        .keyboardType(.numberPad)
                    TextField(loc.t("familyMembers.phoneOptional"), text: $phone)
                        .keyboardType(.numberPad)
                }
                Section(loc.t("familyMembers.medicalNotes")) {
                    TextField(loc.t("familyMembers.allergyChronicOther"), text: $notes, axis: .vertical)
                        .lineLimit(2...5)
                }
            }
            .navigationTitle(loc.t("familyMembers.addTitle"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(loc.t("common.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(loc.t("common.save")) {
                        guard !submitting else { return }
                        submitting = true
                        Task {
                            await onSave(
                                name.trimmingCharacters(in: .whitespaces),
                                relation,
                                phone,
                                gender,
                                Int(ageText),
                                notes
                            )
                            submitting = false
                        }
                    }
                    .disabled(name.trimmingCharacters(in: .whitespaces).isEmpty || submitting)
                }
            }
        }
    }
}
