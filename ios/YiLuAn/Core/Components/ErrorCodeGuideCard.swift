import SwiftUI

/// 错误码引导卡片类型，对应后端 ``app/core/error_codes.py`` 中的三类前置失败：
///
/// - ``phoneRequired``：用户未绑定手机号 → 蓝色卡片 + "去绑定手机号"
/// - ``verificationRequired``：陪诊师资质未通过 → 橙色卡片 + "查看进度"
/// - ``paymentRequired``：订单未支付 → 绿色卡片 + "去支付"
///
/// 这是 D-035 "机器可读错误码 + UX 分层" 决策的 iOS 落地：原 Alert (toast)
/// 表达不出"这是引导，不是结果"的语义；Card 把语义、配色、CTA 三件事合在一起，
/// 让用户一眼就知道下一步该做什么。
///
/// 测试覆盖：``ErrorCodeGuideCardTests`` 验证 code → CardType 映射稳定，
/// 详情见 ``docs/decisions/D-035-machine-readable-error-codes.md``（如未创建则
/// 以晨会纪要 2026-04-22 §四 为准）。
enum ErrorCodeGuideCardType: Equatable {
    case phoneRequired
    case verificationRequired
    case paymentRequired

    /// 从后端机器可读错误码映射到卡片类型。未识别返回 nil（调用方应 fallback 到通用 toast）。
    static func from(errorCode: String?) -> ErrorCodeGuideCardType? {
        switch errorCode {
        case APIErrorCode.phoneRequired:
            return .phoneRequired
        case APIErrorCode.verificationRequired:
            return .verificationRequired
        case APIErrorCode.paymentRequired:
            return .paymentRequired
        default:
            return nil
        }
    }

    /// 主标题
    var title: String {
        switch self {
        case .phoneRequired: return "请先绑定手机号"
        case .verificationRequired: return "资质审核中"
        case .paymentRequired: return "订单尚未支付"
        }
    }

    /// 卡片底色（浅色，便于阅读）
    var backgroundColor: Color {
        switch self {
        case .phoneRequired: return .brandLight
        case .verificationRequired: return .warningLight
        case .paymentRequired: return .successLight
        }
    }

    /// 强调色（左侧色条 + 按钮 + 图标）
    var accentColor: Color {
        switch self {
        case .phoneRequired: return .brand
        case .verificationRequired: return .warning
        case .paymentRequired: return .success
        }
    }

    /// SF Symbol 图标名
    var iconName: String {
        switch self {
        case .phoneRequired: return "iphone.gen3.radiowaves.left.and.right"
        case .verificationRequired: return "clock.badge.checkmark"
        case .paymentRequired: return "creditcard.fill"
        }
    }

    /// CTA 按钮文案
    var ctaTitle: String {
        switch self {
        case .phoneRequired: return "去绑定手机号"
        case .verificationRequired: return "查看进度"
        case .paymentRequired: return "去支付"
        }
    }
}

/// 错误码引导卡片视图，配合 ``ErrorCodeGuideCardType`` 使用。
///
/// 与 ``PhoneRequiredAlert`` 的关系：Alert 仍保留作向后兼容（旧调用点不必立刻迁移），
/// 但**新调用点应优先使用 Card**——它能同时承载色块、图标、CTA 三种 UX 信号。
///
/// 用法：
/// ```swift
/// if let type = ErrorCodeGuideCardType.from(errorCode: vm.lastErrorCode) {
///     ErrorCodeGuideCard(
///         type: type,
///         message: vm.lastErrorMessage ?? "",
///         onPrimary: { handleCTA(type) },
///         onDismiss: { vm.clearError() }
///     )
/// }
/// ```
struct ErrorCodeGuideCard: View {
    let type: ErrorCodeGuideCardType
    let message: String
    var onPrimary: () -> Void = {}
    var onDismiss: () -> Void = {}

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // 左侧色条
            RoundedRectangle(cornerRadius: 2)
                .fill(type.accentColor)
                .frame(width: 4)

            // 图标
            Image(systemName: type.iconName)
                .font(.system(size: 22, weight: .semibold))
                .foregroundColor(type.accentColor)
                .padding(.top, 2)

            // 文本 + CTA
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .top) {
                    Text(type.title)
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundColor(.textPrimary)
                    Spacer()
                    Button(action: onDismiss) {
                        Image(systemName: "xmark")
                            .font(.system(size: 12, weight: .semibold))
                            .foregroundColor(.textHint)
                    }
                    .accessibilityLabel("关闭")
                }
                Text(message)
                    .font(.system(size: 14))
                    .foregroundColor(.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                Button(action: onPrimary) {
                    Text(type.ctaTitle)
                        .font(.system(size: 14, weight: .semibold))
                        .foregroundColor(.white)
                        .padding(.horizontal, 16)
                        .padding(.vertical, 8)
                        .background(type.accentColor)
                        .cornerRadius(8)
                }
                .accessibilityIdentifier("errorCodeGuideCard.cta.\(String(describing: type))")
            }
        }
        .padding(12)
        .background(type.backgroundColor)
        .cornerRadius(12)
        .accessibilityIdentifier("errorCodeGuideCard.\(String(describing: type))")
    }
}

#if DEBUG
struct ErrorCodeGuideCard_Previews: PreviewProvider {
    static var previews: some View {
        VStack(spacing: 16) {
            ErrorCodeGuideCard(type: .phoneRequired, message: "下单前请先绑定手机号，方便陪诊师与您联系。")
            ErrorCodeGuideCard(type: .verificationRequired, message: "您的资质材料已提交，预计 1 个工作日内审核完成。")
            ErrorCodeGuideCard(type: .paymentRequired, message: "请先完成订单支付，陪诊师才能开始服务。")
        }
        .padding()
        .background(Color.bgPage)
    }
}
#endif
