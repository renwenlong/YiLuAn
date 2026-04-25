import SwiftUI

struct PrivacyPolicyView: View {
    @State private var showBackToTop = false

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.lg) {
                    Color.clear.frame(height: 0).id("top")

                    Text("医路安隐私政策")
                        .font(.title2.bold())
                        .frame(maxWidth: .infinity)

                    Text("更新日期：2026年4月10日 | 生效日期：2026年4月10日")
                        .font(.dsCaption)
                        .foregroundStyle(Color.textHint)
                        .frame(maxWidth: .infinity)

                    section("一、引言",
                        "欢迎使用医路安（以下简称\"平台\"或\"我们\"）。我们深知个人信息对您的重要性，并会尽全力保护您的个人信息安全。请您在使用我们的服务前，仔细阅读并了解本隐私政策。")

                    section("二、我们收集的信息", """
                    我们收集以下类型的信息：

                    主动提供的信息：
                    • 手机号码 — 用于注册、登录和验证
                    • 微信授权信息 — 用于微信登录和支付
                    • 患者信息 — 就诊人姓名、联系方式、就诊需求
                    • 陪诊师信息 — 真实姓名、身份证号、资质证书、服务区域

                    自动收集的信息：
                    • 设备信息 — 设备型号、操作系统版本
                    • 日志信息 — 访问时间、使用记录、崩溃日志
                    """)

                    section("三、我们不收集的信息", """
                    我们不会收集以下信息：
                    • 您的通讯录/联系人
                    • 精确地理位置（仅在您授权时获取模糊位置用于就近推荐）
                    • 短信内容
                    • 相册内容（仅在您主动上传头像时访问）
                    """)

                    section("四、信息使用目的", """
                    我们收集和使用您的信息用于以下目的：
                    • 提供陪诊服务 — 匹配患者与陪诊师
                    • 账户管理 — 注册、登录、身份验证
                    • 安全保障 — 风险识别、欺诈防范
                    • 数据分析 — 改善服务质量（匿名化处理）
                    • 客户支持 — 处理投诉和反馈
                    """)

                    section("五、信息共享", """
                    我们仅在以下情况共享您的信息：
                    • 匹配的陪诊师/患者 — 为完成服务所必需的信息
                    • 支付处理方 — 用于处理订单支付
                    • 法律要求 — 应法律法规、法律程序、政府要求而披露

                    我们不会将您的信息出售给任何第三方。
                    """)

                    section("六、信息存储与安全", """
                    • 存储地点 — 中国境内的服务器
                    • 保留期限 — 账号注销后保留 30 天，之后永久删除
                    • 安全措施 — HTTPS 传输加密、数据库加密存储、访问权限控制
                    """)

                    section("七、您的权利", """
                    您拥有以下权利：
                    • 查看和更新个人信息
                    • 删除您的账户和数据
                    • 撤回授权同意
                    • 注销账户 — 您可以随时在"设置"中注销账户
                    """)

                    section("八、未成年人保护",
                        "我们的服务面向 14 周岁以上的用户。我们不会故意收集 14 周岁以下未成年人的个人信息。如果您发现我们无意中收集了未成年人的信息，请联系我们删除。")

                    section("九、Cookie 政策",
                        "本应用使用本地存储而非浏览器 Cookie。我们可能使用类似技术来存储您的偏好设置和登录状态。")

                    section("十、联系我们", """
                    如果您对本隐私政策有任何疑问，请通过以下方式联系我们：
                    • 邮箱：privacy@yiluan.com
                    • 我们将在 15 个工作日内回复您的请求
                    """)

                    Spacer(minLength: 60)
                }
                .padding()
                .background(
                    GeometryReader { geo in
                        Color.clear.preference(
                            key: ScrollOffsetKey.self,
                            value: -geo.frame(in: .named("scroll")).minY
                        )
                    }
                )
            }
            .coordinateSpace(name: "scroll")
            .onPreferenceChange(ScrollOffsetKey.self) { offset in
                withAnimation { showBackToTop = offset > 300 }
            }
            .overlay(alignment: .bottomTrailing) {
                if showBackToTop {
                    Button {
                        withAnimation { proxy.scrollTo("top", anchor: .top) }
                    } label: {
                        VStack(spacing: 2) {
                            Image(systemName: "arrow.up")
                                .font(.system(size: 14, weight: .bold))
                            Text("顶部")
                                .font(.system(size: 9))
                        }
                        .foregroundStyle(Color.brand)
                        .frame(width: 40, height: 40)
                        .background(Color.bgCard)
                        .clipShape(Circle())
                        .shadow(color: .black.opacity(0.12), radius: 8, y: 2)
                    }
                    .padding(.trailing, Spacing.lg)
                    .padding(.bottom, Spacing.xxl)
                    .transition(.scale.combined(with: .opacity))
                }
            }
        }
        .navigationTitle("隐私政策")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func section(_ title: String, _ body: String) -> some View {
        VStack(alignment: .leading, spacing: Spacing.sm) {
            Text(title)
                .font(.dsHeadline)
                .foregroundStyle(Color.textPrimary)
            Text(body)
                .font(.dsBody)
                .foregroundStyle(Color.textSecondary)
                .lineSpacing(4)
        }
    }
}

// MARK: - Scroll offset preference key

struct ScrollOffsetKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = nextValue()
    }
}

#Preview {
    NavigationStack {
        PrivacyPolicyView()
    }
}
