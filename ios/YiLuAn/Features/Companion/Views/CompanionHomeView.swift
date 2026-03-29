import SwiftUI

struct CompanionHomeView: View {
    var body: some View {
        NavigationStack {
            VStack(spacing: 20) {
                // Stats summary
                HStack(spacing: 20) {
                    statCard(title: "今日订单", value: "0")
                    statCard(title: "评分", value: "--")
                    statCard(title: "总订单", value: "0")
                }
                .padding(.horizontal)

                // Placeholder for recent orders
                VStack(alignment: .leading) {
                    Text("我的订单")
                        .font(.headline)
                        .padding(.horizontal)

                    Text("暂无订单")
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity, minHeight: 200)
                }

                Spacer()
            }
            .padding(.top)
            .navigationTitle("陪诊师工作台")
        }
    }

    private func statCard(title: String, value: String) -> some View {
        VStack(spacing: 4) {
            Text(value)
                .font(.title2.bold())
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding()
        .background(Color(.systemGray6))
        .cornerRadius(12)
    }
}

#Preview {
    CompanionHomeView()
}
