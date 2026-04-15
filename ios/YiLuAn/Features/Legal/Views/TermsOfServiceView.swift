import SwiftUI

struct TermsOfServiceView: View {
    @State private var showBackToTop = false

    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                VStack(alignment: .leading, spacing: Spacing.lg) {
                    Color.clear.frame(height: 0).id("top")

                    Text("医路安用户协议")
                        .font(.title2.bold())
                        .frame(maxWidth: .infinity)

                    Text("更新日期：2026年4月10日 | 生效日期：2026年4月10日")
                        .font(.dsCaption)
                        .foregroundStyle(Color.textHint)
                        .frame(maxWidth: .infinity)

                    section("一、总则",
                        "欢迎使用医路安平台（以下简称"本平台"）。本用户协议（以下简称"本协议"）是您与医路安平台之间关于使用本平台服务的法律协议。在使用本平台前，请您仔细阅读本协议。使用本平台即表示您同意接受本协议的所有条款。")

                    section("二、服务内容", """
                    本平台提供以下医疗陪诊服务：
                    • 全程陪诊（¥299）— 陪诊师全程陪同就医
                    • 半程陪诊（¥199）— 陪诊师协助部分就医流程
                    • 代办跑腿（¥149）— 代取报告、代办挂号等

                    本平台为信息撮合平台，为患者和陪诊师之间提供匹配服务。陪诊师以独立身份提供服务，与本平台不存在劳动关系。
                    """)

                    section("三、注册与账户", """
                    注册条件：
                    • 您可以通过手机号码或微信授权注册账户
                    • 注册时须提供真实有效的个人信息
                    • 账户仅限本人使用，不得转让或借用
                    • 您有责任保管好账户安全信息
                    """)

                    section("四、用户行为规范", """
                    使用本平台时，您不得：
                    • 提供虚假信息或冒充他人
                    • 从事违法违规活动
                    • 骚扰、辱骂陪诊师或其他用户
                    • 绕过平台进行私下交易
                    • 利用平台漏洞获取不正当利益
                    """)

                    section("五、订单与支付", """
                    • 支付期限 — 下单后需及时完成支付
                    • 支付方式 — Apple Pay / 微信支付（视平台支持）
                    • 退款规则：
                      - 待接单/已接单状态取消：全额退款
                      - 服务进行中取消：退款 50%
                      - 服务完成后：不予退款
                    """)

                    section("六、陪诊师规范", """
                    陪诊师须遵守以下规范：
                    • 完成实名认证和资质验证
                    • 遵守平台管理规定和服务标准
                    • 保护患者个人隐私信息
                    • 不得向患者推销或收取额外费用
                    """)

                    section("七、知识产权",
                        "本平台所有内容（包括但不限于文字、图片、音频、视频、软件）的知识产权均归本平台所有。未经本平台书面许可，任何人不得以任何方式复制、传播或使用。")

                    section("八、免责声明", """
                    • 本平台不对陪诊服务质量作出保证，服务由陪诊师独立提供
                    • 因不可抗力（自然灾害、政策变更等）导致的服务中断，本平台不承担责任
                    • 用户因自身原因造成的损失，本平台不承担责任
                    """)

                    section("九、协议变更",
                        "本平台有权根据需要修改本协议条款。修改后的协议将在平台上公布。您继续使用本平台即视为接受修改后的协议。")

                    section("十、争议解决",
                        "如因本协议产生争议，双方应首先通过友好协商解决。协商不成的，任何一方均可向本平台所在地有管辖权的人民法院提起诉讼。")

                    section("十一、联系方式", """
                    如有任何问题，请通过以下方式联系我们：
                    • 邮箱：support@yiluan.com
                    • 应用内客服支持
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
        .navigationTitle("用户协议")
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

#Preview {
    NavigationStack {
        TermsOfServiceView()
    }
}
