# YiLuAn iOS — App Store 截图脚本

`generate_screenshots.sh` + `extract_screenshots.py` 用 Xcode UI 测试 + `xcrun simctl` 在多个模拟器上批量截图，整理为 App Store Connect 可直接上传的目录结构。

## 前置条件

- macOS + Xcode 15+
- （推荐）`brew install xcbeautify`
- 仓库内存在 `YiLuAnUITests` target，包含 `AppStoreScreenshots` 测试类，并提供 5 个用例：
  - `test01_Login`
  - `test02_Home`
  - `test03_CompanionDetail`
  - `test04_CreateOrder`
  - `test05_Chat`
- 每个用例结尾把当前屏幕作为 `XCTAttachment` 附加，**lifetime = `keepAlways`**，并用 `attachment.name = "01_login.png"` 这样的 `NN_label.png` 命名。

> 当前仓库尚未创建 `YiLuAnUITests` target / `AppStoreScreenshots` 类。本脚本是**骨架**：先把流水线跑通，等 UI 测试就位即可立刻产出截图。

最小 UI 测试用例参考代码：

```swift
import XCTest

final class AppStoreScreenshots: XCTestCase {
    var app: XCUIApplication!

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments += ["-AppStoreScreenshots", "1"]
        app.launchEnvironment["DEMO_PHONE"] = "13800000001"
        app.launchEnvironment["DEMO_OTP"]   = "000000"
        app.launch()
    }

    func test01_Login() {
        // 等 LoginView 出现，截一张
        XCTAssert(app.staticTexts["登录"].waitForExistence(timeout: 10))
        attach(name: "01_login.png")
    }

    // ... test02_Home / test03_CompanionDetail / test04_CreateOrder / test05_Chat

    private func attach(name: String) {
        let shot = XCUIScreen.main.screenshot()
        let att = XCTAttachment(screenshot: shot)
        att.name = name
        att.lifetime = .keepAlways
        add(att)
    }
}
```

## 运行

```bash
# 默认设备列表 = 6.7" / 6.5" / 5.5" / iPad 12.9"
cd ios
./scripts/generate_screenshots.sh

# 自定义某些设备
DEVICES="iPhone 15 Pro Max,iPad Pro (12.9-inch) (6th generation)" \
  OUT=./screenshots-prod \
  ./scripts/generate_screenshots.sh
```

## 输出

```
screenshots-out/
  6.7-iphone-15-pro-max/01_login.png ... 05_chat.png
  6.5-iphone-11-pro-max/...
  5.5-iphone-8-plus/...
  12.9-ipad-pro-12-9/...
```

每个目录可直接拖入 App Store Connect 的对应尺寸。

## 已知后续

- [ ] 创建真实 UI 测试 target 与 5 个用例
- [ ] 在 CI（macOS runner）夜间跑一次，发现 UI 漂移立即报警
- [ ] 加入"中文 Demo 数据 seeder"，避免审核截图里出现真人医院 logo
- [ ] App Preview 视频脚本（`xcrun simctl io booted recordVideo`）

## 一次性命令

```bash
chmod +x ios/scripts/generate_screenshots.sh ios/scripts/extract_screenshots.py
```
