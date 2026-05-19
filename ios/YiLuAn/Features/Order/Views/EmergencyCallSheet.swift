import SwiftUI
import UIKit

/// [F-03] 订单详情中点击"紧急呼叫"弹出的面板 — 对齐 wechat `pages/patient/order-detail/` 紧急联动。
///
/// 进入时并发拉取：
/// - 紧急联系人列表（最多 3）
/// - 平台客服热线
///
/// 用户点哪一项就走 POST `/emergency/events` 拿到 `phone_to_call`，然后 `UIApplication` 拨出。
struct EmergencyCallSheet: View {
    let orderId: String

    @Environment(\.dismiss) private var dismiss
    @State private var contacts: [EmergencyContact] = []
    @State private var hotline: String = ""
    @State private var isLoading = true
    @State private var triggering = false
    @State private var errorMessage: String?

    var body: some View {
        NavigationView {
            Group {
                if isLoading {
                    ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
                } else {
                    listContent
                }
            }
            .navigationTitle("紧急呼叫")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("关闭") { dismiss() }
                }
            }
            .alert("提示", isPresented: .constant(errorMessage != nil)) {
                Button("好") { errorMessage = nil }
            } message: {
                Text(errorMessage ?? "")
            }
            .task { await load() }
        }
    }

    private var listContent: some View {
        List {
            Section(header: Text("紧急联系人").font(.caption)) {
                if contacts.isEmpty {
                    Text("还没有添加紧急联系人")
                        .foregroundColor(.secondary)
                        .font(.subheadline)
                    NavigationLink {
                        EmergencyContactsView()
                    } label: {
                        Label("去添加", systemImage: "plus.circle")
                    }
                } else {
                    ForEach(contacts) { c in
                        Button {
                            Task { await triggerContact(c) }
                        } label: {
                            contactRow(c)
                        }
                        .buttonStyle(.plain)
                        .disabled(triggering)
                    }
                }
            }

            Section(header: Text("平台客服").font(.caption)) {
                Button {
                    Task { await triggerHotline() }
                } label: {
                    HStack {
                        Image(systemName: "phone.fill.arrow.up.right")
                            .foregroundColor(.red)
                        VStack(alignment: .leading) {
                            Text("呼叫平台客服")
                                .font(.headline)
                            if !hotline.isEmpty {
                                Text(hotline)
                                    .font(.caption)
                                    .foregroundColor(.secondary)
                            }
                        }
                        Spacer()
                    }
                    .padding(.vertical, 4)
                }
                .buttonStyle(.plain)
                .disabled(triggering || hotline.isEmpty)
            }

            Section {
                Text("点击后将立即拨打对应号码，并向后台记录一条紧急事件用于审计与回溯。")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        }
    }

    private func contactRow(_ c: EmergencyContact) -> some View {
        HStack {
            Image(systemName: "phone.circle.fill")
                .foregroundColor(.red)
            VStack(alignment: .leading) {
                Text("\(c.name) · \(c.relationship)").font(.headline)
                Text(c.phone)
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
            Spacer()
        }
        .padding(.vertical, 4)
    }

    // MARK: - Actions

    private func load() async {
        isLoading = true
        defer { isLoading = false }
        async let contactsTask = (try? EmergencyService.listContacts()) ?? []
        async let hotlineTask = (try? EmergencyService.hotline())?.hotline ?? ""
        let (c, h) = await (contactsTask, hotlineTask)
        contacts = c
        hotline = h
    }

    private func triggerContact(_ c: EmergencyContact) async {
        await fire(body: EmergencyTriggerRequest(orderId: orderId, contactId: c.id, hotline: false))
    }

    private func triggerHotline() async {
        await fire(body: EmergencyTriggerRequest(orderId: orderId, contactId: nil, hotline: true))
    }

    private func fire(body: EmergencyTriggerRequest) async {
        guard !triggering else { return }
        triggering = true
        defer { triggering = false }
        do {
            let resp = try await EmergencyService.trigger(body)
            await MainActor.run {
                dismiss()
                placeCall(to: resp.phoneToCall)
            }
        } catch {
            errorMessage = (error as? LocalizedError)?.errorDescription ?? "呼叫失败"
        }
    }

    private func placeCall(to number: String) {
        let cleaned = number.filter { $0.isNumber || $0 == "+" }
        guard let url = URL(string: "tel://\(cleaned)") else { return }
        if UIApplication.shared.canOpenURL(url) {
            UIApplication.shared.open(url)
        }
    }
}
