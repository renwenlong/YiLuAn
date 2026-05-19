import SwiftUI

/// F-05: 家人 / 实际就诊人列表与新增（最小 MVP）。
/// 下单页 picker 与详情展示在后续 iOS 迭代中补全（追踪：TD-IOS-FAMILY-PICKER）。
struct FamilyMembersView: View {
    @StateObject private var viewModel = FamilyMembersViewModel()
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
                    Text("还没有添加家人")
                        .foregroundColor(.secondary)
                    Text("添加后，可在下单时为家人预约陪诊")
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
        .navigationTitle("我的家人")
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
        .alert("提示", isPresented: .constant(viewModel.errorMessage != nil)) {
            Button("好") { viewModel.errorMessage = nil }
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
    @State private var name = ""
    @State private var relation = "parent"
    @State private var phone = ""
    @State private var gender = "unknown"
    @State private var ageText = ""
    @State private var notes = ""
    @State private var submitting = false

    private let relations: [(String, String)] = [
        ("parent", "父母"), ("spouse", "配偶"), ("child", "子女"),
        ("sibling", "兄弟姐妹"), ("grandparent", "祖父母"),
        ("relative", "亲戚"), ("friend", "朋友"), ("other", "其他"),
    ]

    var body: some View {
        NavigationView {
            Form {
                Section("基本信息") {
                    TextField("姓名", text: $name)
                    Picker("关系", selection: $relation) {
                        ForEach(relations, id: \.0) { Text($0.1).tag($0.0) }
                    }
                    Picker("性别", selection: $gender) {
                        Text("未填").tag("unknown")
                        Text("男").tag("male")
                        Text("女").tag("female")
                    }
                    TextField("年龄（可选）", text: $ageText)
                        .keyboardType(.numberPad)
                    TextField("手机号（可选）", text: $phone)
                        .keyboardType(.numberPad)
                }
                Section("就医备注") {
                    TextField("过敏 / 慢病 / 其它", text: $notes, axis: .vertical)
                        .lineLimit(2...5)
                }
            }
            .navigationTitle("添加家人")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
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
