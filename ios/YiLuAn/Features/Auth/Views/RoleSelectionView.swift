import SwiftUI

struct RoleSelectionView: View {
    @EnvironmentObject var authViewModel: AuthViewModel
    @EnvironmentObject var loc: LocalizationManager

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Text(loc.t("role.selectTitle"))
                .font(.title.bold())
            Text(loc.t("role.selectSubtitle"))
                .foregroundStyle(.secondary)

            VStack(spacing: 16) {
                roleCard(
                    title: loc.t("role.iamPatient"),
                    subtitle: loc.t("role.patientDesc"),
                    icon: "person.fill",
                    role: .patient
                )
                roleCard(
                    title: loc.t("role.iamCompanion"),
                    subtitle: loc.t("role.companionDesc"),
                    icon: "stethoscope",
                    role: .companion
                )
            }
            .padding(.horizontal)

            Spacer()
            Spacer()
        }
    }

    private func roleCard(title: String, subtitle: String, icon: String, role: UserRole) -> some View {
        Button {
            Task { await authViewModel.setRole(role) }
        } label: {
            HStack(spacing: 16) {
                Image(systemName: icon)
                    .font(.title)
                    .frame(width: 50, height: 50)
                    .background(Color.blue.opacity(0.1))
                    .clipShape(Circle())

                VStack(alignment: .leading) {
                    Text(title)
                        .font(.headline)
                    Text(subtitle)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .foregroundStyle(.secondary)
            }
            .padding()
            .background(Color(.systemGray6))
            .cornerRadius(12)
        }
        .buttonStyle(.plain)
    }
}

#Preview {
    RoleSelectionView()
        .environmentObject(AuthViewModel())
        .environmentObject(LocalizationManager.shared)
}
