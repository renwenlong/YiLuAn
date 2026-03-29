import SwiftUI

struct RoleSelectionView: View {
    @EnvironmentObject var authViewModel: AuthViewModel

    var body: some View {
        VStack(spacing: 32) {
            Spacer()

            Text("选择您的角色")
                .font(.title.bold())
            Text("请选择您使用医路安的方式")
                .foregroundStyle(.secondary)

            VStack(spacing: 16) {
                roleCard(
                    title: "我是患者",
                    subtitle: "需要陪诊服务",
                    icon: "person.fill",
                    role: .patient
                )
                roleCard(
                    title: "我是陪诊师",
                    subtitle: "提供陪诊服务",
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
}
