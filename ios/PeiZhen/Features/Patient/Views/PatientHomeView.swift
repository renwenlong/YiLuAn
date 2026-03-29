import SwiftUI

struct PatientHomeView: View {
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 20) {
                    // Service cards
                    VStack(alignment: .leading, spacing: 12) {
                        Text("选择服务")
                            .font(.headline)

                        LazyVGrid(columns: [
                            GridItem(.flexible()),
                            GridItem(.flexible()),
                            GridItem(.flexible())
                        ], spacing: 12) {
                            ForEach(ServiceType.allCases, id: \.rawValue) { service in
                                serviceCard(service)
                            }
                        }
                    }
                    .padding(.horizontal)

                    // Placeholder for recommended companions
                    VStack(alignment: .leading) {
                        Text("推荐陪诊师")
                            .font(.headline)
                            .padding(.horizontal)

                        Text("暂无推荐")
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, minHeight: 100)
                    }
                }
                .padding(.top)
            }
            .navigationTitle("医路安")
        }
    }

    private func serviceCard(_ service: ServiceType) -> some View {
        VStack(spacing: 8) {
            Image(systemName: serviceIcon(service))
                .font(.title2)
                .foregroundStyle(.blue)
            Text(service.displayName)
                .font(.caption)
            Text("¥\(service.price as NSDecimalNumber)")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 16)
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }

    private func serviceIcon(_ service: ServiceType) -> String {
        switch service {
        case .fullAccompany: return "person.2.fill"
        case .halfAccompany: return "person.fill"
        case .errand: return "doc.text.fill"
        }
    }
}

#Preview {
    PatientHomeView()
}
