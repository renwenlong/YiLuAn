import Foundation
import SwiftUI

/// 家属端 share OTP 流程 ViewModel（S2-INT-004 / F2 OTP UI）
///
/// 流程状态机：
///   `.enterPhone` → 用户输入手机号
///   `.sendingOTP` → 调 ShareService.sendShareOTP
///   `.enterOTP`   → 短信码 6 位输入（masked phone 提示）
///   `.exchanging` → 调 ShareService.exchangeShareSession
///   `.success`    → share_session 已存 Keychain，可拉脱敏视图
///   `.failure(msg)` → 任意一步失败 + 错误文案
///
/// 状态转移由 ViewModel 单向驱动，不抛 Error 让 View 解析。
@MainActor
final class ShareOTPViewModel: ObservableObject {

    enum Stage: Equatable {
        case enterPhone
        case sendingOTP
        case enterOTP(maskedPhone: String, expiresIn: Int)
        case exchanging
        case success(SavedSession)
        case failure(message: String)

        /// 等价 ShareSessionStore.SavedSession（避免跨模块依赖在 enum 关联值里）
        struct SavedSession: Equatable {
            let orderId: UUID
            let scope: ShareScope
        }
    }

    // MARK: - Inputs

    /// 短链 token（40 字符），由 UniversalLink / 手输入构造时传入
    let shareToken: String

    @Published var phone: String = ""
    @Published var otp: String = ""

    @Published private(set) var stage: Stage = .enterPhone

    // MARK: - Init

    init(shareToken: String) {
        self.shareToken = shareToken
    }

    // MARK: - Step 1：发 OTP

    func sendOTP() async {
        guard !phone.isEmpty else {
            stage = .failure(message: LocalizationManager.shared.t("share.errPhoneRequired"))
            return
        }
        stage = .sendingOTP
        do {
            let resp = try await ShareService.sendShareOTP(token: shareToken, phone: phone)
            stage = .enterOTP(maskedPhone: resp.maskedPhone, expiresIn: resp.expiresIn)
        } catch {
            stage = .failure(message: extractMessage(from: error, default: LocalizationManager.shared.t("share.errOtpSendFailed")))
        }
    }

    // MARK: - Step 2：换 share_session

    func exchangeSession() async {
        guard otp.count == 6 else {
            stage = .failure(message: LocalizationManager.shared.t("share.errOtpRequired"))
            return
        }
        stage = .exchanging
        do {
            let resp = try await ShareService.exchangeShareSession(
                token: shareToken,
                phone: phone,
                otp: otp
            )
            // 落 Keychain（30min TTL）
            ShareSessionStore.save(response: resp, shareToken: shareToken)
            stage = .success(
                .init(orderId: resp.orderId, scope: resp.shareScope)
            )
        } catch {
            stage = .failure(message: extractMessage(from: error, default: LocalizationManager.shared.t("share.errVerifyFailed")))
        }
    }

    // MARK: - 重置（输错后回到输入页）

    func resetToEnterPhone() {
        otp = ""
        stage = .enterPhone
    }

    func resetToEnterOTP() {
        if case .failure = stage {
            // 失败回到 OTP 输入页（若 phone 已发码）；否则回手机页
            if !phone.isEmpty {
                // 我们没保留之前的 masked phone / expires，给一个空 prompt 但保留 phone
                stage = .enterOTP(maskedPhone: maskPhone(phone), expiresIn: 0)
            } else {
                stage = .enterPhone
            }
        }
    }

    // MARK: - Helpers

    /// 本地脱敏（接口失败回退；正常用后端返回的 masked_phone）
    nonisolated func maskPhone(_ raw: String) -> String {
        let s = raw.replacingOccurrences(of: " ", with: "")
        guard s.count >= 7 else { return s }
        let prefix = String(s.prefix(3))
        let suffix = String(s.suffix(4))
        return "\(prefix)****\(suffix)"
    }

    private func extractMessage(from error: Error, default fallback: String) -> String {
        if let apiErr = error as? APIError, let msg = apiErr.errorDescription, !msg.isEmpty {
            return msg
        }
        return fallback
    }
}
