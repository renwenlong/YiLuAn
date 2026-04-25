import Foundation
import Security

enum KeychainManager {
    enum KeychainError: Error {
        case duplicateEntry
        case itemNotFound
        case unexpectedStatus(OSStatus)
        case dataConversionError
    }

    // In-memory fallback used when the Keychain is unavailable (e.g. unit-test
    // bundles without a host application return errSecMissingEntitlement = -34018).
    // This keeps semantics consistent without weakening production storage.
    private static var memoryStore: [String: String] = [:]
    private static let memoryQueue = DispatchQueue(label: "KeychainManager.memoryStore")

    private static func memoryGet(_ key: String) -> String? {
        memoryQueue.sync { memoryStore[key] }
    }
    private static func memorySet(_ key: String, _ value: String) {
        memoryQueue.sync { memoryStore[key] = value }
    }
    private static func memoryDelete(_ key: String) {
        _ = memoryQueue.sync { memoryStore.removeValue(forKey: key) }
    }

    static func save(key: String, value: String) throws {
        guard let data = value.data(using: .utf8) else {
            throw KeychainError.dataConversionError
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecValueData as String: data
        ]

        // Delete existing item first
        SecItemDelete(query as CFDictionary)

        let status = SecItemAdd(query as CFDictionary, nil)
        if status == errSecSuccess {
            memoryDelete(key) // keep fallback in sync
            return
        }
        // Fallback for environments where the Keychain isn't accessible
        // (notably XCTest bundles without a host app: errSecMissingEntitlement -34018).
        if status == errSecMissingEntitlement || status == errSecNotAvailable {
            memorySet(key, value)
            return
        }
        throw KeychainError.unexpectedStatus(status)
    }

    static func get(key: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var result: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &result)

        if status == errSecSuccess,
           let data = result as? Data,
           let string = String(data: data, encoding: .utf8) {
            return string
        }
        // Fall back to in-memory store when Keychain is unavailable or the
        // item was previously written via the fallback path.
        return memoryGet(key)
    }

    static func delete(key: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrAccount as String: key
        ]
        SecItemDelete(query as CFDictionary)
        memoryDelete(key)
    }

    // MARK: - Convenience for tokens

    static var accessToken: String? {
        get { get(key: AppConfig.accessTokenKey) }
        set {
            if let value = newValue {
                try? save(key: AppConfig.accessTokenKey, value: value)
            } else {
                delete(key: AppConfig.accessTokenKey)
            }
        }
    }

    static var refreshToken: String? {
        get { get(key: AppConfig.refreshTokenKey) }
        set {
            if let value = newValue {
                try? save(key: AppConfig.refreshTokenKey, value: value)
            } else {
                delete(key: AppConfig.refreshTokenKey)
            }
        }
    }

    static func clearTokens() {
        delete(key: AppConfig.accessTokenKey)
        delete(key: AppConfig.refreshTokenKey)
    }
}
