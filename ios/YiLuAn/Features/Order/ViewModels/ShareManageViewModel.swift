import Foundation
import SwiftUI

/// 患者端 Share 发起管理 ViewModel（发起端 Owner 路径）。
/// ANDROID-DEV-B7-IOS-SHARE-ENTRY — 补齐 iOS 发起端 UI，对齐小程序 WX-SHARE 发起端 (#395)。
///
/// 职责：createShare 生成分享链接 / listShares 列出 active / revokeShare 撤销。
/// 后端约束：同订单 active token 上限 3，第 4 个自动 revoke 最老一枚。
/// 状态单向驱动，不抛 Error 让 View 解析。
@MainActor
final class ShareManageViewModel: ObservableObject {

    let orderId: String

    @Published var scope: ShareScope = .full
    @Published private(set) var shares: [OrderShareToken] = []
    @Published private(set) var activeCount: Int = 0
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var isCreating: Bool = false
    @Published private(set) var revokingId: UUID?
    @Published var errorMessage: String?

    init(orderId: String) {
        self.orderId = orderId
    }

    /// 拉取当前 active 分享列表。
    func loadShares() async {
        isLoading = true
        defer { isLoading = false }
        do {
            let resp = try await ShareService.listShares(orderId: orderId)
            shares = resp.items
            activeCount = resp.shareActiveCount
        } catch {
            errorMessage = LocalizationManager.shared.t("shareEntry.errLoadFailed")
        }
    }

    /// 创建分享链接。成功后重拉列表（后端可能自动 revoke 最老一枚）。
    /// 返回新建的 share_url 供调用方复制到剪贴板。
    func createShare() async -> String? {
        guard !isCreating else { return nil }
        isCreating = true
        defer { isCreating = false }
        do {
            let resp = try await ShareService.createShare(orderId: orderId, scope: scope)
            await loadShares()
            return resp.shareURL
        } catch {
            errorMessage = LocalizationManager.shared.t("shareEntry.errCreateFailed")
            return nil
        }
    }

    /// 撤销单个分享 token。
    func revokeShare(tokenId: UUID) async {
        revokingId = tokenId
        defer { revokingId = nil }
        do {
            try await ShareService.revokeShare(orderId: orderId, tokenId: tokenId.uuidString)
            await loadShares()
        } catch {
            errorMessage = LocalizationManager.shared.t("shareEntry.errRevokeFailed")
        }
    }
}
