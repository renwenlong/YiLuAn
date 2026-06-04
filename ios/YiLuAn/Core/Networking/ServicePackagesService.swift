import Foundation

/// S2-REQ-003-P5c — 公开服务档位（GET /api/v1/public/service-packages）
///
/// 端点公开访问 (无 auth)，admin 改价/上下架后客户端动态生效。
/// 单元测 + 集成测见 ServicePackagesServiceTests.
struct ServicePackage: Codable, Identifiable, Equatable {
    let code: String
    let name: String
    let price: Decimal
    let sortOrder: Int
    let description: String?

    /// `true` 表示该实例来自降级 fallback（API 不可达），UI 可据此显示降级提示。
    /// 后端 JSON 不返该字段；Codable 解码默认为 false。
    var isFallback: Bool = false

    var id: String { code }

    enum CodingKeys: String, CodingKey {
        case code
        case name
        case price
        case sortOrder = "sort_order"
        case description
    }

    init(
        code: String,
        name: String,
        price: Decimal,
        sortOrder: Int,
        description: String? = nil,
        isFallback: Bool = false
    ) {
        self.code = code
        self.name = name
        self.price = price
        self.sortOrder = sortOrder
        self.description = description
        self.isFallback = isFallback
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        self.code = try container.decode(String.self, forKey: .code)
        self.name = try container.decode(String.self, forKey: .name)
        // price 后端返字符串 "299.00" 或数字 299；两种都接受
        if let priceStr = try? container.decode(String.self, forKey: .price) {
            self.price = Decimal(string: priceStr) ?? 0
        } else if let priceDouble = try? container.decode(Double.self, forKey: .price) {
            self.price = Decimal(priceDouble)
        } else {
            self.price = 0
        }
        self.sortOrder = (try? container.decode(Int.self, forKey: .sortOrder)) ?? 0
        self.description = try? container.decode(String.self, forKey: .description)
        self.isFallback = false
    }
}

/// 拉公开服务档位列表 + 降级 fallback。
///
/// 用法：
/// ```
/// let packages = await ServicePackagesService.shared.list()
/// // 若 packages.first?.isFallback == true → 显示 "服务列表已降级" 提示
/// ```
final class ServicePackagesService {
    static let shared = ServicePackagesService()

    /// 与 wechat/services/servicePackages.js FALLBACK_PACKAGES + iOS ServiceType enum 三档一致。
    /// API 不可达 / 空返 / 解码失败时使用，保证基础下单可用。
    static let fallbackPackages: [ServicePackage] = [
        ServicePackage(
            code: "full_accompany", name: "全程陪诊",
            price: Decimal(299), sortOrder: 10, isFallback: true
        ),
        ServicePackage(
            code: "half_accompany", name: "半程陪诊",
            price: Decimal(199), sortOrder: 20, isFallback: true
        ),
        ServicePackage(
            code: "errand", name: "代办跑腿",
            price: Decimal(149), sortOrder: 30, isFallback: true
        ),
    ]

    private let client: APIClient

    init(client: APIClient = APIClient.shared) {
        self.client = client
    }

    /// 拉公开档位列表。Never throws — API 失败时返 fallback。
    /// acceptance #4 降级兜底硬要求。
    func list() async -> [ServicePackage] {
        do {
            let packages: [ServicePackage] = try await client.request(.publicServicePackages)
            guard !packages.isEmpty else {
                return Self.fallbackPackages
            }
            // 客户端兜底再按 sort_order 排序
            return packages.sorted { $0.sortOrder < $1.sortOrder }
        } catch {
            return Self.fallbackPackages
        }
    }
}
