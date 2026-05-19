import SwiftUI

/// [F-07] 我的复诊提醒列表（按 remind_at 升序）。
struct FollowupRemindersView: View {
    @StateObject private var viewModel = FollowupRemindersViewModel()

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.reminders.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if viewModel.reminders.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "bell.badge")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text("还没有复诊提醒")
                        .foregroundColor(.secondary)
                    Text("在已完成订单详情中可以创建复诊提醒")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(viewModel.reminders) { r in
                        VStack(alignment: .leading, spacing: 6) {
                            HStack {
                                Text(formatDate(r.remindAt)).font(.headline)
                                Spacer()
                                Text(r.statusLabel)
                                    .font(.caption)
                                    .padding(.horizontal, 8).padding(.vertical, 2)
                                    .background(statusColor(r.status).opacity(0.15))
                                    .foregroundColor(statusColor(r.status))
                                    .cornerRadius(6)
                            }
                            if let note = r.note, !note.isEmpty {
                                Text(note)
                                    .font(.subheadline)
                                    .foregroundColor(.secondary)
                                    .lineLimit(3)
                            }
                            Text("订单 #\(r.orderId.prefix(8))")
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 4)
                        .swipeActions {
                            if r.canCancel {
                                Button("取消", role: .destructive) {
                                    Task { await viewModel.cancel(r) }
                                }
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle("我的复诊提醒")
        .navigationBarTitleDisplayMode(.inline)
        .alert("提示", isPresented: .constant(viewModel.errorMessage != nil)) {
            Button("好") { viewModel.errorMessage = nil }
        } message: {
            Text(viewModel.errorMessage ?? "")
        }
        .task { await viewModel.load() }
        .refreshable { await viewModel.load() }
    }

    private func formatDate(_ d: Date) -> String {
        let fmt = DateFormatter()
        fmt.locale = Locale(identifier: "zh_CN")
        fmt.dateFormat = "yyyy-MM-dd HH:mm"
        return fmt.string(from: d)
    }

    private func statusColor(_ s: String) -> Color {
        switch s {
        case "pending":   return .orange
        case "sent":      return .green
        case "cancelled": return .gray
        case "failed":    return .red
        default:          return .secondary
        }
    }
}

/// [F-07] 在订单详情中点击"复诊提醒"弹出的创建表单。
/// 仅当订单状态为 completed/reviewed 才会显示入口。
struct FollowupReminderCreateSheet: View {
    let orderId: String
    /// 创建成功后回调，便于父视图刷新或弹 toast。
    let onCreated: () -> Void

    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel = FollowupRemindersViewModel()
    @State private var remindAt: Date = Calendar.current.date(byAdding: .day, value: 7, to: Date()) ?? Date()
    @State private var note: String = ""
    @State private var submitting = false

    var body: some View {
        NavigationView {
            Form {
                Section("提醒时间") {
                    DatePicker(
                        "提醒时间",
                        selection: $remindAt,
                        in: Date()...,
                        displayedComponents: [.date, .hourAndMinute]
                    )
                    .environment(\.locale, Locale(identifier: "zh_CN"))
                }
                Section("备注") {
                    TextField("如：复诊取报告、复查血常规…（最多 140 字）", text: $note, axis: .vertical)
                        .lineLimit(2...5)
                }
                Section {
                    Text("到点后会以微信订阅消息推送到你（订阅消息授权请在小程序内完成）。")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle("创建复诊提醒")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("取消") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("创建") {
                        guard !submitting else { return }
                        submitting = true
                        Task {
                            let ok = await viewModel.create(
                                orderId: orderId,
                                remindAt: remindAt,
                                note: note.isEmpty ? nil : note
                            )
                            submitting = false
                            if ok {
                                onCreated()
                                dismiss()
                            }
                        }
                    }
                    .disabled(submitting || remindAt <= Date())
                }
            }
            .alert("提示", isPresented: .constant(viewModel.errorMessage != nil)) {
                Button("好") { viewModel.errorMessage = nil }
            } message: {
                Text(viewModel.errorMessage ?? "")
            }
        }
    }
}
