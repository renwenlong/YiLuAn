import SwiftUI

/// [F-07] 我的复诊提醒列表（按 remind_at 升序）。
struct FollowupRemindersView: View {
    @StateObject private var viewModel = FollowupRemindersViewModel()
    @EnvironmentObject var loc: LocalizationManager

    var body: some View {
        Group {
            if viewModel.isLoading && viewModel.reminders.isEmpty {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if viewModel.reminders.isEmpty {
                VStack(spacing: 12) {
                    Image(systemName: "bell.badge")
                        .font(.system(size: 48))
                        .foregroundColor(.secondary)
                    Text(loc.t("followupReminders.empty"))
                        .foregroundColor(.secondary)
                    Text(loc.t("order.createReminderFromCompleted"))
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
                            Text(loc.t("order.orderNo", String(r.orderId.prefix(8))))
                                .font(.caption2)
                                .foregroundColor(.secondary)
                        }
                        .padding(.vertical, 4)
                        .swipeActions {
                            if r.canCancel {
                                Button(loc.t("common.cancel"), role: .destructive) {
                                    Task { await viewModel.cancel(r) }
                                }
                            }
                        }
                    }
                }
            }
        }
        .navigationTitle(loc.t("order.myFollowUpReminders"))
        .navigationBarTitleDisplayMode(.inline)
        .alert(loc.t("dialog.tip"), isPresented: .constant(viewModel.errorMessage != nil)) {
            Button(loc.t("order.ok")) { viewModel.errorMessage = nil }
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
    @EnvironmentObject var loc: LocalizationManager
    @State private var remindAt: Date = Calendar.current.date(byAdding: .day, value: 7, to: Date()) ?? Date()
    @State private var note: String = ""
    @State private var submitting = false

    var body: some View {
        NavigationView {
            Form {
                Section(loc.t("order.reminderTime")) {
                    DatePicker(
                        loc.t("order.reminderTime"),
                        selection: $remindAt,
                        in: Date()...,
                        displayedComponents: [.date, .hourAndMinute]
                    )
                    .environment(\.locale, Locale(identifier: "zh_CN"))
                }
                Section(loc.t("orderDetail.notesLabel")) {
                    TextField(loc.t("order.notesExample"), text: $note, axis: .vertical)
                        .lineLimit(2...5)
                }
                Section {
                    Text(loc.t("order.subscribeMessageNotice"))
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
            }
            .navigationTitle(loc.t("orderDetail.createFollowup"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(loc.t("common.cancel")) { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button(loc.t("order.create")) {
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
            .alert(loc.t("dialog.tip"), isPresented: .constant(viewModel.errorMessage != nil)) {
                Button(loc.t("order.ok")) { viewModel.errorMessage = nil }
            } message: {
                Text(viewModel.errorMessage ?? "")
            }
        }
    }
}
