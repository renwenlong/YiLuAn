# YiLuAn iOS App

## Setup

This iOS project requires creating the Xcode project on macOS:

1. Open Xcode → Create New Project → App
2. Product Name: `YiLuAn`
3. Organization Identifier: `com.yiluan`
4. Interface: SwiftUI, Language: Swift
5. Save into the `ios/` directory
6. Delete the auto-generated `ContentView.swift`
7. Add all existing Swift files from `YiLuAn/` to the project

All source files are pre-written:

```
YiLuAn/
├── YiLuAnApp.swift              # App entry point
├── Configuration/
│   └── AppConfig.swift           # API URLs, keys, pricing
├── Core/
│   ├── Networking/
│   │   ├── APIClient.swift       # URLSession async wrapper + JWT refresh
│   │   ├── APIEndpoint.swift     # All API endpoints
│   │   └── WebSocketClient.swift # WebSocket + auto-reconnect
│   ├── Storage/
│   │   └── KeychainManager.swift # Secure token storage
│   ├── Extensions/
│   │   └── View+Extensions.swift # Common View modifiers
│   └── Models/
│       ├── User.swift            # User, PatientProfile, CompanionProfile
│       ├── Order.swift           # Order, ServiceType, OrderStatus
│       ├── Hospital.swift
│       ├── ChatMessage.swift
│       ├── Review.swift
│       ├── Notification.swift
│       └── AuthModels.swift      # Request/response DTOs
├── Features/
│   ├── Auth/
│   │   ├── ViewModels/AuthViewModel.swift
│   │   └── Views/{LoginView, OTPInputView, RoleSelectionView}.swift
│   ├── Patient/Views/PatientHomeView.swift
│   ├── Companion/Views/CompanionHomeView.swift
│   └── Profile/Views/ProfileView.swift
└── SharedViews/
    └── MainTabView.swift
```

## Deployment Target

iOS 17.0+

## Architecture

MVVM with Combine. APIClient uses async/await with automatic JWT token refresh.
