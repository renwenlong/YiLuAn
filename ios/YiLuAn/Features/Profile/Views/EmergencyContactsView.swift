import SwiftUI

/// [F-03] 紧急联系人列表与编辑 — 对齐 wechat `pages/profile/emergency-contacts/`。
/// 限制：最多 3 个联系人；超出/重复手机后端返回 409。
struct EmergencyContactsView: View {
    @StateObject private var viewModel = EmergencyContactsViewModel()
    @State private var sheetMode: SheetMode?

    enum SheetMode: Identifiable {
        case create
        case edit(EmergencyContact)

        var id: String {
            switch self {
            case .create: return "create"
            case .edit(let c): return "edit-\(c.id)"
            }
        }
    }

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.contacts.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if viewModel.contacts.isEmpty {
                emptyState
            } else {
                contactList
            }
        }
        .navigationTitle("紧急联系人")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Button {
                    sheetMode = .create
                } label: {
                    Image(systemName: "plus")
                }
                .disabled(!viewModel.canAddMore)
            }
        }
        .sheet(item: $sheetMode) { mode in
            switch mode {
            case .create:
                EmergencyContactEditSheet(
                    title: "添加紧急联系人",
                    initial: nil
                ) { name, phone, relationship in
                    let ok = await viewModel.create(name: name, phone: phone, relationship: relationship)
                    if ok { sheetMode = nil }
                }
            case .edit(let contact):
                EmergencyContactEditSheet(
                    title: "编辑联系人",
                    initial: contact
                ) { name, phone, relationship in
                    let ok = await viewModel.update(id: contact.id, name: name, phone: phone, relationship: relationship)
                    if ok { sheetMode = nil }
                }
            }
        }
        .alert("提示", isPresented: .constant(viewModel.errorMessage != nil)) {
            Button("好") { viewModel.errorMessage = nil }
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
        .task { await viewModel.load() }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "person.crop.circle.badge.exclamationmark")
                .font(.system(size: 48))
                .foregroundColor(.secondary)
            Text("还没有紧急联系人")
                .foregroundColor(.secondary)
            Text("最多 3 位，服务进行中可一键呼叫")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var contactList: some View {
        List {
            Section {
                ForEach(viewModel.contacts) { contact in
                    Button {
                        sheetMode = .edit(contact)
                    } label: {
                        contactRow(contact)
                    }
                    .buttonStyle(.plain)
                }
                .onDelete { offsets in
                    Task {
                        for index in offsets {
                            await viewModel.delete(viewModel.contacts[index])
                        }
                    }
                }
            } footer: {
                Text("最多 3 位 · 当前 \(viewModel.contacts.count)/3")
                    .font(.caption)
            }
        }
    }

    private func contactRow(_ c: EmergencyContact) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(c.name).font(.headline)
                    Text("·").foregroundColor(.secondary)
                    Text(c.relationship)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                Text(c.phone)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
            Image(systemName: "chevron.right")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 4)
    }
}

private struct EmergencyContactEditSheet: View {
    let title: String
    let initial: EmergencyContact?
    let onSave: (_ name: String, _ phone: String, _ relationship: String) async -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var name = ""
    @State private var phone = ""
    @State private var relationship = "配偶"
    @State private var submitting = false

    var body: some View {
        NavigationView {
            Form {
                Section("基本信息") {
                    TextField("姓名", text: $name)
                    TextField("手机号", text: $phone)
                        .keyboardType(.numberPad)
                    Picker("关系", selection: $relationship) {
                        ForEach(EmergencyRelationship.presets, id: \.self) { r in
                            Text(r).tag(r)
                        }
                    }
                }
                Section {
                    Text("紧急联系人会在你触发紧急呼叫时显示，并由你选择拨打。")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("保存") {
                        guard !submitting, isValid else { return }
                        submitting = true
                        Task {
                            await onSave(name, phone, relationship)
                            submitting = false
                        }
                    }
                    .disabled(!isValid || submitting)
                }
            }
            .onAppear {
                if let c = initial {
                    name = c.name
                    phone = c.phone
                    relationship = c.relationship
                }
            }
        }
    }

    private var isValid: Bool {
        let trimmedName = name.trimmingCharacters(in: .whitespaces)
        let trimmedPhone = phone.trimmingCharacters(in: .whitespaces)
        guard !trimmedName.isEmpty else { return false }
        // 与后端正则一致：1[3-9]\d{9}
        let pattern = #"^1[3-9]\d{9}$"#
        return trimmedPhone.range(of: pattern, options: .regularExpression) != nil
    }
}
