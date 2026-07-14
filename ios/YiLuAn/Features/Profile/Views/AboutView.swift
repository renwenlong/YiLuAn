import SwiftUI

struct AboutView: View {
    @EnvironmentObject var loc: LocalizationManager
    var body: some View {
        ScrollView {
            VStack(spacing: Spacing.xl) {
                Spacer().frame(height: Spacing.xxl)

                // Logo
                Image(systemName: "cross.case.fill")
                    .font(.system(size: 72))
                    .foregroundStyle(Color.brand)

                VStack(spacing: Spacing.sm) {
                    Text(loc.t("login.appName"))
                        .font(.title.bold())
                    Text("YiLuAn")
                        .font(.dsSubheadline)
                        .foregroundStyle(.secondary)
                }

                // Version
                Text(loc.t("profile.versionPrefix") + " " + (Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0.0"))
                    .font(.dsCaption)
                    .foregroundStyle(Color.textHint)

                // Description
                VStack(alignment: .leading, spacing: Spacing.lg) {
                    descriptionSection(
                        title: loc.t("profile.aboutUs"),
                        content: loc.t("profile.aboutIntro")
                    )

                    descriptionSection(
                        title: loc.t("profile.ourServices"),
                        content: loc.t("profile.serviceTiersDescription")
                    )

                    descriptionSection(
                        title: loc.t("profile.contactUs"),
                        content: loc.t("profile.supportContactInfo")
                    )
                }
                .padding(.horizontal)

                Spacer()

                Text(loc.t("profile.copyright"))
                    .font(.dsCaption)
                    .foregroundStyle(Color.textHint)
                    .padding(.bottom)
            }
        }
        .navigationTitle(loc.t("profile.aboutUs"))
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
