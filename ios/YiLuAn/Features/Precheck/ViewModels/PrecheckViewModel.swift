import Foundation
import Combine

/// Precheck ViewModel — 4 信任卡状态管理 + WS 推送 + polling fallback
///
/// **S3-DEV-003-TRUST-UI-IOS (方案 B canonical — 纯 Swift Native)**
///
/// 设计:
/// 1. `loadInitial(orderId:)` — view onAppear, HTTP GET 拉初始 summary + 启动 WS
/// 2. WS 收到任一 event → 触发 `refresh()` (HTTP GET 拿最新 summary, WS event 仅作 invalidate 信号)
/// 3. WS 断开 → 切到 30s polling fallback (PRD-003 v0.4 §S3-REQ-003)
/// 4. WS 恢复 → 停 polling
///
/// 决策依据:
/// - WS event payload 不携带完整 4 card 状态 (只是 invalidate 信号), 故必须 HTTP refresh
/// - signed URL TTL ≤15min, polling 30s 足够触发 refresh URL
/// - design §6.2 原本要 WKWebView + React, 已 pivot 方案 B (魈 08:00Z 拍板)
@MainActor
final class PrecheckViewModel: ObservableObject {

    // MARK: - Published state

    @Published private(set) var summary: OrderPrecheckSummary?
    @Published private(set) var isLoading: Bool = false
    @Published private(set) var errorMessage: String?
    @Published private(set) var wsConnected: Bool = false
    @Published private(set) var isPollingFallback: Bool = false

    // MARK: - Inputs

    private let orderId: String

    // MARK: - Internal

    private var webSocket: PrecheckWebSocket?
    private var pollingTimer: Timer?
    private let pollingInterval: TimeInterval

    /// Test injection seam: override service for unit tests.
    var serviceFetch: (String) async throws -> OrderPrecheckSummary = PrecheckService.fetchPrecheckStatus

    init(orderId: String, pollingInterval: TimeInterval = 30) {
        self.orderId = orderId
        self.pollingInterval = pollingInterval
    }

    deinit {
        // deinit 不能用 @MainActor 隔离方法, 直接 invalidate
        pollingTimer?.invalidate()
        pollingTimer = nil
    }

    // MARK: - Public lifecycle

    /// View onAppear — 拉初始 summary + 启动 WS.
    func loadInitial() async {
        await refresh()
        connectWebSocket()
    }

    /// View onDisappear — 关 WS + 停 polling.
    func teardown() {
        webSocket?.disconnect()
        webSocket = nil
        wsConnected = false
        stopPolling()
    }

    /// HTTP refresh (WS event 触发 / polling tick 触发 / 用户下拉触发).
    ///
    /// **历史订单 fallback** (S3-DEV-003-TRUST-UI-IOS 起手第一时间发现):
    /// 后端 404 = 订单不存在 OR S3 之前的历史订单 (无 4 信任卡 record).
    /// 后者不应该阫断付款, 故 `summary` 仍为 nil 但不设 errorMessage,
    /// View 层拿不到 paymentEnabled 读取 → onChange 不触发 →
    /// 父 OrderDetailView 需在 contractId == nil 时是否依赖 precheck 闸门自判 (另外处理).
    func refresh() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            summary = try await serviceFetch(orderId)
        } catch APIError.httpError(let code, _) where code == 404 {
            // 历史订单 — 不报错, summary 留 nil, 付款判断由父 View 接管
            summary = nil
            errorMessage = nil
        } catch let err as APIError {
            errorMessage = err.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - WS

    private func connectWebSocket() {
        let ws = PrecheckWebSocket(orderId: orderId)
        ws.onAuthOK = { [weak self] in
            Task { @MainActor [weak self] in
                self?.wsConnected = true
                self?.stopPolling()  // WS 上线即停 polling
            }
        }
        ws.onEvent = { [weak self] event in
            Task { @MainActor [weak self] in
                // 3 个 event 都触发 HTTP refresh — payload 不携带完整 summary
                await self?.refresh()
            }
        }
        ws.onClose = { [weak self] code, reason in
            Task { @MainActor [weak self] in
                self?.wsConnected = false

                // 永久失败 (auth / authz 错): 不 fallback polling, 报错给上层
                if code == 4001 || code == 4003 || code == 4004 || code == 4011 {
                    self?.errorMessage = "WS 鉴权失败 (code \(code)): \(reason)"
                    return
                }

                // 临时失败 (idle / network / unknown): 切 polling fallback
                self?.startPolling()
            }
        }
        ws.connect()
        webSocket = ws
    }

    // MARK: - Polling fallback (WS 断时 30s 兜底)

    private func startPolling() {
        guard pollingTimer == nil else { return }
        isPollingFallback = true
        pollingTimer = Timer.scheduledTimer(
            withTimeInterval: pollingInterval,
            repeats: true
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                await self?.refresh()
            }
        }
    }

    private func stopPolling() {
        pollingTimer?.invalidate()
        pollingTimer = nil
        isPollingFallback = false
    }
}
