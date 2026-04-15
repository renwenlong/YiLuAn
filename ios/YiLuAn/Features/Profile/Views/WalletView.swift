import SwiftUI

struct WalletSummary: Decodable {
    let balance: Decimal
    let totalIncome: Decimal
    let withdrawn: Decimal
}

struct WalletTransaction: Decodable, Identifiable {
    let id: String
    let type: String
    let amount: Decimal
    let description: String?
    let createdAt: Date

    var typeLabel: String {
        switch type {
        case "payment": return "支付"
        case "income": return "收入"
        case "refund": return "退款"
        default: return type
        }
    }

    var typeColor: Color {
        switch type {
        case "payment": return .danger
        case "income": return .success
        case "refund": return .warning
        default: return .textSecondary
        }
    }

    var amountPrefix: String {
        switch type {
        case "payment": return "-"
        case "income": return "+"
        case "refund": return "+"
        default: return ""
        }
    }
}

struct WalletTransactionListResponse: Decodable {
    let items: [WalletTransaction]
    let total: Int
}

@MainActor
class WalletViewModel: ObservableObject {
    @Published var summary: WalletSummary?
    @Published var transactions: [WalletTransaction] = []
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var total = 0
    private var currentPage = 1

    func loadSummary() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            summary = try await APIClient.shared.request(.wallet)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadTransactions(page: Int = 1) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let queryItems = [
                URLQueryItem(name: "page", value: "\(page)"),
                URLQueryItem(name: "page_size", value: "20")
            ]
            let response: WalletTransactionListResponse = try await APIClient.shared.request(
                .walletTransactions, queryItems: queryItems
            )
            if page == 1 {
                transactions = response.items
            } else {
                transactions.append(contentsOf: response.items)
            }
            total = response.total
            currentPage = page
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func loadMore() async {
        guard transactions.count < total else { return }
        await loadTransactions(page: currentPage + 1)
    }
}

struct WalletView: View {
    @StateObject private var viewModel = WalletViewModel()

    var body: some View {
        ScrollView {
            VStack(spacing: Spacing.lg) {
                // Balance Card
                VStack(spacing: Spacing.lg) {
                    Text("账户余额（元）")
                        .font(.dsSubheadline)
                        .foregroundStyle(.white.opacity(0.8))
                    Text(String(format: "%.2f", NSDecimalNumber(decimal: viewModel.summary?.balance ?? 0).doubleValue))
                        .font(.system(size: 36, weight: .bold))
                        .foregroundStyle(.white)

                    HStack(spacing: Spacing.xxl) {
                        VStack(spacing: Spacing.xs) {
                            Text("总收入")
                                .font(.dsCaption)
                                .foregroundStyle(.white.opacity(0.7))
                            Text(String(format: "¥%.2f", NSDecimalNumber(decimal: viewModel.summary?.totalIncome ?? 0).doubleValue))
                                .font(.dsHeadline)
                                .foregroundStyle(.white)
                        }
                        VStack(spacing: Spacing.xs) {
                            Text("已提现")
                                .font(.dsCaption)
                                .foregroundStyle(.white.opacity(0.7))
                            Text(String(format: "¥%.2f", NSDecimalNumber(decimal: viewModel.summary?.withdrawn ?? 0).doubleValue))
                                .font(.dsHeadline)
                                .foregroundStyle(.white)
                        }
                    }
                }
                .frame(maxWidth: .infinity)
                .padding(Spacing.xl)
                .background(
                    LinearGradient(
                        colors: [Color.brand, Color(hex: 0x096DD9)],
                        startPoint: .topLeading,
                        endPoint: .bottomTrailing
                    )
                )
                .cornerRadius(CornerRadius.lg)
                .padding(.horizontal)

                // Transactions
                VStack(alignment: .leading, spacing: Spacing.md) {
                    Text("交易记录")
                        .font(.dsHeadline)
                        .padding(.horizontal)

                    if viewModel.transactions.isEmpty && !viewModel.isLoading {
                        Text("暂无交易记录")
                            .font(.dsBody)
                            .foregroundStyle(Color.textHint)
                            .frame(maxWidth: .infinity, minHeight: 100)
                    } else {
                        LazyVStack(spacing: 0) {
                            ForEach(viewModel.transactions) { tx in
                                transactionRow(tx)
                                Divider().padding(.horizontal)
                            }
                        }
                    }
                }
            }
            .padding(.top)
        }
        .navigationTitle("钱包")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await viewModel.loadSummary()
            await viewModel.loadTransactions()
        }
        .refreshable {
            await viewModel.loadSummary()
            await viewModel.loadTransactions()
        }
    }

    private func transactionRow(_ tx: WalletTransaction) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: Spacing.xs) {
                Text(tx.typeLabel)
                    .font(.dsBody)
                Text(tx.description ?? "")
                    .font(.dsCaption)
                    .foregroundStyle(Color.textHint)
                    .lineLimit(1)
            }
            Spacer()
            VStack(alignment: .trailing, spacing: Spacing.xs) {
                Text("\(tx.amountPrefix)¥\(String(format: "%.2f", NSDecimalNumber(decimal: tx.amount).doubleValue))")
                    .font(.dsHeadline)
                    .foregroundStyle(tx.typeColor)
                Text(tx.createdAt, style: .date)
                    .font(.dsCaption)
                    .foregroundStyle(Color.textHint)
            }
        }
        .padding(.horizontal)
        .padding(.vertical, Spacing.md)
    }
}

#Preview {
    NavigationStack {
        WalletView()
    }
}
