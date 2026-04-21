# YiLuAn iOS App

> **重要**：iOS 工程文件 `YiLuAn.xcodeproj` **不入仓**（`.gitignore` 忽略），由 [XcodeGen](https://github.com/yonaskolb/XcodeGen) 从 `project.yml` 声明式生成。源代码新增/删除自动同步，CI 与本地保持一致。

## Setup（首次运行 / 新机器）

### 1. 安装 XcodeGen（一次性，使用 Homebrew）

```bash
brew install xcodegen
```

### 2. 生成 `.xcodeproj`

```bash
cd ios
xcodegen generate
```

每次新增 / 删除 Swift 文件后重跑此命令；CI 会自动跑。

### 3. 用 Xcode 打开

```bash
open YiLuAn.xcodeproj
```

## 跑测试

### 命令行（与 CI 一致）

```bash
cd ios
xcodebuild test \
  -project YiLuAn.xcodeproj \
  -scheme YiLuAn \
  -destination 'platform=iOS Simulator,name=iPhone 15,OS=latest' \
  -resultBundlePath TestResults.xcresult \
  CODE_SIGNING_ALLOWED=NO
```

### Xcode UI

⌘ + U

## CI

- Workflow：`.github/workflows/ios-tests.yml`
- 触发：push to `main`（仅 ios/ 改动）、PR（仅 ios/ 改动）、手动 `workflow_dispatch`
- Runner：`macos-latest`（GitHub Actions 免费 macOS quota）

## 修改 iOS 工程结构

**不要**在 Xcode UI 里手动改工程设置（target / build settings / scheme）——会被下次 `xcodegen generate` 覆盖。

正确做法：编辑 `project.yml` → `xcodegen generate` → commit `project.yml`。

`project.yml` 文档：<https://github.com/yonaskolb/XcodeGen/blob/master/Docs/ProjectSpec.md>

## 工程结构

```
YiLuAn/
├── YiLuAnApp.swift              # App 入口
├── Info.plist                    # 由 project.yml 引用
├── Configuration/
│   └── AppConfig.swift           # API URL、密钥、价格配置
├── Core/
│   ├── Networking/               # APIClient + APIEndpoint + WebSocketClient
│   ├── Storage/                  # KeychainManager
│   ├── Extensions/               # View 扩展、设计系统
│   └── Models/                   # User / Order / Hospital / ChatMessage 等 DTO
├── Features/                     # MVVM 按业务域拆分
│   ├── Auth/                     # 登录、OTP、角色选择
│   ├── Patient/                  # 患者主页与个人资料
│   ├── Companion/                # 陪诊师主页、列表、详情、个人资料
│   ├── Order/                    # 订单创建、列表、详情、可接单池
│   ├── Chat/                     # 聊天列表与房间
│   ├── Notifications/            # 通知列表
│   ├── Payment/                  # 支付结果
│   ├── Profile/                  # 个人资料、关于、绑定手机、钱包
│   ├── Review/                   # 评价
│   ├── Settings/                 # 设置、注销账号
│   └── Legal/                    # 隐私政策、服务条款
└── SharedViews/
    └── MainTabView.swift
```

## Deployment Target

iOS 17.0+

## 架构

MVVM + Combine。`APIClient` 使用 async/await，自动 JWT token 刷新。
