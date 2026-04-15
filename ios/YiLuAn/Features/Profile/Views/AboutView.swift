import SwiftUI

struct AboutView: View {
    var body: some View {
        ScrollView {
            VStack(spacing: Spacing.xl) {
                Spacer().frame(height: Spacing.xxl)

                // Logo
                Image(systemName: "cross.case.fill")
                    .font(.system(size: 72))
                    .foregroundStyle(Color.brand)

                VStack(spacing: Spacing.sm) {
                    Text("医路安")
                        .font(.title.bold())
                    Text("YiLuAn")
                        .font(.dsSubheadline)
                        .foregroundStyle(.secondary)
                }

                // Version
                Text("版本 \(Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0")")
                    .font(.dsCaption)
                    .foregroundStyle(Color.textHint)

                // Description
                VStack(alignment: .leading, spacing: Spacing.lg) {
                    descriptionSection(
                        title: "关于我们",
                        content: "医路安是专业的医疗陪诊服务平台，致力于为患者提供温暖、专业的就医陪伴服务。我们连接需要医院陪诊的患者与专业陪诊师，让就医不再孤单。"
                    )

                    descriptionSection(
                        title: "我们的服务",
                        content: "• 全程陪诊（¥299）— 全程陪同就医\n• 半程陪诊（¥199）— 部分环节陪同\n• 代办跑腿（¥149）— 代取报告等"
                    )

                    descriptionSection(
                        title: "联系我们",
                        content: "客服电话：400-888-0000\n客服邮箱：support@yiluan.app\n工作时间：周一至周五 9:00-18:00"
                    )
                }
                .padding(.horizontal)

                Spacer()

                Text("© 2026 医路安科技有限公司")
                    .font(.dsCaption)
                    .foregroundStyle(Color.textHint)
                    .padding(.bottom)
            }
        }
        .navigationTitle("关于我们")
        .navigationBarTitleDisplayMode(.inline)
    }

    private func descriptionSection(title: String, content: String) -> some View {
        VStack(alignment: .leading, spacing: Spacing.sm) {
            Text(title)
                .font(.dsHeadline)
            Text(content)
                .font(.dsBody)
                .foregroundStyle(Color.textSecondary)
        }
    }
}

#Preview {
    NavigationStack {
        AboutView()
    }
}
