import Foundation

/// 巨字号缩放表唯一真源（PRD §F5 / iOS 端）
///
/// 真源：`docs/design/wireframes/U1-folding-stepper/README.md` §「巨字号缩放表」
/// **与微信端 `wechat/utils/fontScale.js` 双端 token 完整一致**（非仅按钮，逐项取值）。
///
/// 用法：View 根据 `@AppStorage("huge_font")` 切换 `FontScale.tokens(huge:)`，
/// 用 token 数值（点数 / pt）绑定字号、按钮高、间距等。
enum FontScale {
    /// 缩放表（钉死 · 非等比逐项取值，与微信 TABLE 同源）
    /// 取值约定：[常规, 巨字号]，单位 pt（微信端是 px，iOS 端直接复用同等数值）
    private static let table: [String: [CGFloat]] = [
        "bodyFont": [14, 18],         // 正文字号
        "metaFont": [12, 15],         // 次要字号（摘要 / meta）
        "primaryBtnH": [42, 50],      // 主按钮高
        "labelMarginTop": [12, 15],   // 行内间距 label 上
        "labelMarginBottom": [6, 8],  // 行内间距 label 下
        "stepNum": [22, 26],          // 步骤头 num 圆点
    ]

    /// 巨字号下摘要行的最大行数。
    /// - 常规：单行省略
    /// - 巨字号：两行截断 + 「…」
    static func summaryClamp(huge: Bool) -> Int {
        huge ? 2 : 1
    }

    /// 当前模式下全部 token 数值。
    static func tokens(huge: Bool) -> FontScaleTokens {
        let idx = huge ? 1 : 0
        return FontScaleTokens(
            bodyFont: table["bodyFont"]![idx],
            metaFont: table["metaFont"]![idx],
            primaryBtnH: table["primaryBtnH"]![idx],
            labelMarginTop: table["labelMarginTop"]![idx],
            labelMarginBottom: table["labelMarginBottom"]![idx],
            stepNum: table["stepNum"]![idx],
            summaryClamp: summaryClamp(huge: huge)
        )
    }
}

/// 一组缩放 token 的数值快照。
struct FontScaleTokens: Equatable {
    let bodyFont: CGFloat
    let metaFont: CGFloat
    let primaryBtnH: CGFloat
    let labelMarginTop: CGFloat
    let labelMarginBottom: CGFloat
    let stepNum: CGFloat
    let summaryClamp: Int
}
