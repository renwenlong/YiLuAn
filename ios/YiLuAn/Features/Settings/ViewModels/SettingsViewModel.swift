import SwiftUI

struct DeleteAccountRequest: Encodable {
    let code: String
}

@MainActor
class SettingsViewModel: ObservableObject {
    @Published var otpCode = ""
    @Published var isConfirmed = false
    @Published var isSendingOTP = false
    @Published var isDeletingAccount = false
    @Published var otpCountdown = 0
    @Published var pressCountdown = 3
    @Published var isPressing = false
    @Published var errorMessage: String?
    @Published var cacheSize: String = "0 MB"

    private var otpTimer: Timer?
    private var pressTimer: Timer?

    var canSendOTP: Bool {
        otpCountdown == 0 && !isSendingOTP
    }

    var canDelete: Bool {
        otpCode.count == 6 && isConfirmed && !isDeletingAccount
    }

    func calculateCacheSize() {
        let cacheURL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
        guard let cacheURL else {
            cacheSize = "0 MB"
            return
        }
        let size = (try? FileManager.default.allocatedSizeOfDirectory(at: cacheURL)) ?? 0
        let formatter = ByteCountFormatter()
        formatter.countStyle = .file
        cacheSize = formatter.string(fromByteCount: Int64(size))
    }

    func clearCache() {
        guard let cacheURL = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first else { return }
        try? FileManager.default.removeItem(at: cacheURL)
        try? FileManager.default.createDirectory(at: cacheURL, withIntermediateDirectories: true)
        calculateCacheSize()
    }

    func sendOTP(phone: String) async {
        isSendingOTP = true
        errorMessage = nil
        defer { isSendingOTP = false }

        do {
            let request = SendOTPRequest(phone: phone)
            try await APIClient.shared.requestVoid(.sendOTP, body: request)
            startOTPCountdown()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func deleteAccount(phone: String) async -> Bool {
        isDeletingAccount = true
        errorMessage = nil
        defer { isDeletingAccount = false }

        do {
            let body = DeleteAccountRequest(code: otpCode)
            try await APIClient.shared.requestVoid(.deleteAccount, body: body)
            return true
        } catch {
            errorMessage = error.localizedDescription
            return false
        }
    }

    func startOTPCountdown() {
        otpCountdown = 60
        otpTimer?.invalidate()
        otpTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] timer in
            Task { @MainActor in
                guard let self else { timer.invalidate(); return }
                self.otpCountdown -= 1
                if self.otpCountdown <= 0 {
                    timer.invalidate()
                    self.otpCountdown = 0
                }
            }
        }
    }

    func startPressCountdown() {
        isPressing = true
        pressCountdown = 3
        pressTimer?.invalidate()
        pressTimer = Timer.scheduledTimer(withTimeInterval: 1, repeats: true) { [weak self] timer in
            Task { @MainActor in
                guard let self else { timer.invalidate(); return }
                self.pressCountdown -= 1
                if self.pressCountdown <= 0 {
                    timer.invalidate()
                }
            }
        }
    }

    func cancelPress() {
        isPressing = false
        pressCountdown = 3
        pressTimer?.invalidate()
    }

    func cleanup() {
        otpTimer?.invalidate()
        pressTimer?.invalidate()
    }
}

// MARK: - FileManager extension for cache size

extension FileManager {
    func allocatedSizeOfDirectory(at url: URL) throws -> UInt64 {
        var size: UInt64 = 0
        let resourceKeys: Set<URLResourceKey> = [.fileSizeKey, .isDirectoryKey]
        guard let enumerator = enumerator(at: url, includingPropertiesForKeys: Array(resourceKeys)) else {
            return 0
        }
        for case let fileURL as URL in enumerator {
            let resourceValues = try fileURL.resourceValues(forKeys: resourceKeys)
            if resourceValues.isDirectory != true {
                size += UInt64(resourceValues.fileSize ?? 0)
            }
        }
        return size
    }
}
