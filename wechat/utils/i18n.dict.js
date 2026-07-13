// utils/i18n.dict.js
// I18N-DEV-002 — 微信端字典镜像（自 docs/i18n/dictionary.json 生成，key 集强制一致）
//
// ⚠ 勿手改此文件。主字典 SSoT = docs/i18n/dictionary.json（DEV-001 产出）。
// 微信小程序无法 require 仓库根 JSON，故本目录维护 CommonJS 镜像。
// 同步方式：node scripts/gen-i18n-dict.js（本期）；主字典变更后重新生成并提交。

module.exports = {
  "common": {
    "confirm": {
      "zh-Hans": "确认",
      "en": "Confirm"
    },
    "cancel": {
      "zh-Hans": "取消",
      "en": "Cancel"
    },
    "submit": {
      "zh-Hans": "提交",
      "en": "Submit"
    },
    "back": {
      "zh-Hans": "返回",
      "en": "Back"
    },
    "save": {
      "zh-Hans": "保存",
      "en": "Save"
    },
    "delete": {
      "zh-Hans": "删除",
      "en": "Delete"
    },
    "edit": {
      "zh-Hans": "编辑",
      "en": "Edit"
    },
    "loading": {
      "zh-Hans": "加载中...",
      "en": "Loading..."
    },
    "notSet": {
      "zh-Hans": "未设置",
      "en": "Not Set"
    },
    "notBound": {
      "zh-Hans": "未绑定",
      "en": "Not Bound"
    },
    "retry": {
      "zh-Hans": "重试",
      "en": "Retry"
    }
  },
  "settings": {
    "title": {
      "zh-Hans": "设置",
      "en": "Settings"
    },
    "language": {
      "zh-Hans": "语言",
      "en": "Language"
    },
    "languageZh": {
      "zh-Hans": "简体中文",
      "en": "简体中文"
    },
    "languageEn": {
      "zh-Hans": "English",
      "en": "English"
    },
    "general": {
      "zh-Hans": "通用",
      "en": "General"
    },
    "version": {
      "zh-Hans": "版本",
      "en": "Version"
    },
    "clearCache": {
      "zh-Hans": "清除缓存",
      "en": "Clear Cache"
    },
    "privacyPolicy": {
      "zh-Hans": "隐私政策",
      "en": "Privacy Policy"
    },
    "termsOfService": {
      "zh-Hans": "用户协议",
      "en": "Terms of Service"
    },
    "logout": {
      "zh-Hans": "退出登录",
      "en": "Log Out"
    },
    "myCity": {
      "zh-Hans": "我的城市",
      "en": "My City"
    },
    "myPhone": {
      "zh-Hans": "我的手机号",
      "en": "My Phone"
    },
    "about": {
      "zh-Hans": "关于",
      "en": "About"
    },
    "deleteAccount": {
      "zh-Hans": "注销账号",
      "en": "Delete Account"
    },
    "selectCity": {
      "zh-Hans": "选择城市",
      "en": "Select City"
    },
    "autoLocate": {
      "zh-Hans": "自动定位",
      "en": "Auto Locate"
    },
    "availableCities": {
      "zh-Hans": "可选城市",
      "en": "Available Cities"
    }
  },
  "role": {
    "patient": {
      "zh-Hans": "患者",
      "en": "Patient"
    },
    "companion": {
      "zh-Hans": "陪诊师",
      "en": "Companion"
    },
    "familyMember": {
      "zh-Hans": "家属",
      "en": "Family Member"
    },
    "switchTo": {
      "zh-Hans": "切换为{targetRole}",
      "en": "Switch to {targetRole}",
      "_params": [
        "targetRole"
      ]
    },
    "current": {
      "zh-Hans": "当前：{role}",
      "en": "Current: {role}",
      "_params": [
        "role"
      ]
    },
    "selectTitle": {
      "zh-Hans": "选择您的身份",
      "en": "Select Your Role"
    },
    "selectSubtitle": {
      "zh-Hans": "请选择您的使用身份，后续可在设置中更改",
      "en": "Choose how you'll use the app. You can change this later in Settings."
    },
    "iamPatient": {
      "zh-Hans": "我是患者",
      "en": "I'm a Patient"
    },
    "iamCompanion": {
      "zh-Hans": "我是陪诊师",
      "en": "I'm a Companion"
    },
    "patientDesc": {
      "zh-Hans": "寻找专业陪诊师",
      "en": "Find a professional companion"
    },
    "companionDesc": {
      "zh-Hans": "接单赚取收入",
      "en": "Take orders and earn income"
    },
    "patientBadge": {
      "zh-Hans": "患",
      "en": "P"
    },
    "companionBadge": {
      "zh-Hans": "陪",
      "en": "C"
    }
  },
  "order": {
    "title": {
      "zh-Hans": "订单",
      "en": "Order"
    },
    "wallet": {
      "zh-Hans": "钱包",
      "en": "Wallet"
    },
    "hospital": {
      "zh-Hans": "医院",
      "en": "Hospital"
    },
    "emergencyContact": {
      "zh-Hans": "紧急联系人",
      "en": "Emergency Contact"
    },
    "myOrders": {
      "zh-Hans": "我的订单",
      "en": "My Orders"
    },
    "noOrders": {
      "zh-Hans": "暂无订单",
      "en": "No Orders"
    },
    "emptyHint": {
      "zh-Hans": "下单后可在此查看进度",
      "en": "Track your order progress here after booking"
    },
    "countUnit": {
      "zh-Hans": "{count} 个订单",
      "en": "{count} order(s)",
      "_params": [
        "count"
      ],
      "_note": "English 单复数本期采 order(s) 折中 (PRD §7.5 已接受，AC-5 认可)"
    }
  },
  "orderStatus": {
    "created": {
      "zh-Hans": "待接单",
      "en": "Pending"
    },
    "accepted": {
      "zh-Hans": "已接单",
      "en": "Accepted"
    },
    "in_progress": {
      "zh-Hans": "进行中",
      "en": "In Progress"
    },
    "completed": {
      "zh-Hans": "已完成",
      "en": "Completed"
    },
    "reviewed": {
      "zh-Hans": "已评价",
      "en": "Reviewed"
    },
    "cancelled_by_patient": {
      "zh-Hans": "患者取消",
      "en": "Cancelled by Patient"
    },
    "cancelled_by_companion": {
      "zh-Hans": "陪诊师取消",
      "en": "Cancelled by Companion"
    },
    "rejected_by_companion": {
      "zh-Hans": "陪诊师拒单",
      "en": "Rejected by Companion"
    },
    "expired": {
      "zh-Hans": "已过期",
      "en": "Expired"
    }
  },
  "refundState": {
    "refunded": {
      "zh-Hans": "已退款",
      "en": "Refunded",
      "_note": "退款子状态独立维度 (ADR-0041 解耦)，非 orderStatus"
    }
  },
  "serviceType": {
    "full_accompany": {
      "zh-Hans": "全程陪诊",
      "en": "Full Accompaniment"
    },
    "half_accompany": {
      "zh-Hans": "半程陪诊",
      "en": "Half Accompaniment"
    },
    "errand": {
      "zh-Hans": "代办跑腿",
      "en": "Errand Service"
    }
  },
  "login": {
    "title": {
      "zh-Hans": "登录",
      "en": "Log In"
    },
    "phone": {
      "zh-Hans": "手机号",
      "en": "Phone Number"
    },
    "getCode": {
      "zh-Hans": "获取验证码",
      "en": "Get Code"
    },
    "codeLabel": {
      "zh-Hans": "验证码",
      "en": "Verification Code"
    },
    "appName": {
      "zh-Hans": "医路安",
      "en": "YiLuAn"
    },
    "appDesc": {
      "zh-Hans": "专业医疗陪诊服务",
      "en": "Professional Medical Escort Service"
    },
    "wechatLogin": {
      "zh-Hans": "微信一键登录",
      "en": "Log in with WeChat"
    },
    "phoneLogin": {
      "zh-Hans": "手机号登录",
      "en": "Log in with Phone"
    },
    "submit": {
      "zh-Hans": "登录",
      "en": "Log In"
    },
    "inputPhone": {
      "zh-Hans": "请输入手机号",
      "en": "Enter phone number"
    },
    "inputCode": {
      "zh-Hans": "请输入6位验证码",
      "en": "Enter 6-digit code"
    },
    "agreementPre": {
      "zh-Hans": "我已阅读并同意",
      "en": "I have read and agree to the"
    },
    "userAgreement": {
      "zh-Hans": "《用户协议》",
      "en": "User Agreement"
    },
    "and": {
      "zh-Hans": "和",
      "en": "and"
    },
    "privacyPolicy": {
      "zh-Hans": "《隐私政策》",
      "en": "Privacy Policy"
    }
  },
  "otp": {
    "sentTo": {
      "zh-Hans": "验证码已发送至 +86 {phone}",
      "en": "Code sent to +86 {phone}",
      "_params": [
        "phone"
      ]
    }
  },
  "createOrder": {
    "hugeFont": {
      "zh-Hans": "巨字号",
      "en": "Large Font"
    },
    "notSelected": {
      "zh-Hans": "未选择",
      "en": "Not selected"
    },
    "nextStep": {
      "zh-Hans": "下一步",
      "en": "Next"
    },
    "serviceFallback": {
      "zh-Hans": "⚠️ 服务列表已降级，使用默认 3 档",
      "en": "⚠️ Service list degraded, using 3 default tiers"
    },
    "stepService": {
      "zh-Hans": "服务类型",
      "en": "Service Type"
    },
    "stepHospital": {
      "zh-Hans": "医院",
      "en": "Hospital"
    },
    "stepDate": {
      "zh-Hans": "日期",
      "en": "Date"
    },
    "stepPatient": {
      "zh-Hans": "患者与陪诊师",
      "en": "Patient & Companion"
    },
    "change": {
      "zh-Hans": "更换",
      "en": "Change"
    },
    "selectHospital": {
      "zh-Hans": "选择医院",
      "en": "Select Hospital"
    },
    "department": {
      "zh-Hans": "科室（可选）",
      "en": "Department (optional)"
    },
    "noDepartment": {
      "zh-Hans": "不选择科室",
      "en": "No department"
    },
    "dateLabel": {
      "zh-Hans": "日期",
      "en": "Date"
    },
    "selectDate": {
      "zh-Hans": "请选择日期",
      "en": "Select a date"
    },
    "period": {
      "zh-Hans": "时段",
      "en": "Period"
    },
    "morning": {
      "zh-Hans": "上午",
      "en": "Morning"
    },
    "afternoon": {
      "zh-Hans": "下午",
      "en": "Afternoon"
    },
    "orderFor": {
      "zh-Hans": "给谁下单",
      "en": "Order for"
    },
    "manageFamily": {
      "zh-Hans": "管理家人",
      "en": "Manage Family"
    },
    "assignCompanion": {
      "zh-Hans": "指定陪诊师",
      "en": "Assigned Companion"
    },
    "reselect": {
      "zh-Hans": "重新选择",
      "en": "Reselect"
    },
    "completedOrders": {
      "zh-Hans": "已完成 {count} 单",
      "en": "{count} orders completed",
      "_params": [
        "count"
      ]
    },
    "notesOptional": {
      "zh-Hans": "备注（可选）",
      "en": "Notes (optional)"
    },
    "notesPlaceholder": {
      "zh-Hans": "请描述您的需求，如症状等",
      "en": "Describe your needs, e.g. symptoms"
    },
    "confirmOrder": {
      "zh-Hans": "确认下单",
      "en": "Confirm Order"
    },
    "selectCompanion": {
      "zh-Hans": "选择陪诊师",
      "en": "Select Companion"
    },
    "verified": {
      "zh-Hans": "已认证",
      "en": "Verified"
    },
    "noMatchCompanion": {
      "zh-Hans": "暂无匹配的陪诊师",
      "en": "No matching companions"
    },
    "finishStepFirst": {
      "zh-Hans": "请先完成本步",
      "en": "Please complete this step first"
    },
    "confirmBack": {
      "zh-Hans": "是否回改？",
      "en": "Go back to edit?"
    },
    "confirmBackContent": {
      "zh-Hans": "下游已选数据将保留",
      "en": "Your later selections will be kept"
    },
    "missingService": {
      "zh-Hans": "缺少服务类型",
      "en": "Service type missing"
    },
    "missingHospital": {
      "zh-Hans": "缺少医院信息",
      "en": "Hospital info missing"
    },
    "selectDateTime": {
      "zh-Hans": "请选择日期和时间",
      "en": "Please select date and time"
    },
    "bindPhoneTitle": {
      "zh-Hans": "请先绑定手机号",
      "en": "Bind your phone number first"
    },
    "bindPhoneContent": {
      "zh-Hans": "下单前需要绑定手机号，方便陪诊师联系您",
      "en": "You need to bind a phone number before ordering so the companion can contact you"
    },
    "goBind": {
      "zh-Hans": "去绑定",
      "en": "Bind Now"
    },
    "orderSuccess": {
      "zh-Hans": "订单创建成功",
      "en": "Order created successfully"
    },
    "createFailed": {
      "zh-Hans": "创建失败",
      "en": "Failed to create order"
    },
    "self": {
      "zh-Hans": "本人",
      "en": "Myself"
    }
  },
  "home": {
    "title": {
      "zh-Hans": "首页",
      "en": "Home"
    },
    "greeting": {
      "zh-Hans": "你好",
      "en": "Hello"
    },
    "selectHospital": {
      "zh-Hans": "选择医院",
      "en": "Select Hospital"
    },
    "clearSelection": {
      "zh-Hans": "清除选择",
      "en": "Clear"
    },
    "searchHospital": {
      "zh-Hans": "搜索医院名称",
      "en": "Search hospital name"
    },
    "noHospitalFound": {
      "zh-Hans": "暂未找到相关医院，换个关键词试试吧",
      "en": "No hospitals found. Try a different keyword."
    },
    "selectService": {
      "zh-Hans": "选择服务",
      "en": "Select Service"
    },
    "tapSelectService": {
      "zh-Hans": "点击选择服务类型",
      "en": "Tap to select a service type"
    },
    "clearFilter": {
      "zh-Hans": "清除筛选",
      "en": "Clear Filter"
    },
    "recommendedCompanions": {
      "zh-Hans": "推荐陪诊师",
      "en": "Recommended Companions"
    },
    "matchedCompanions": {
      "zh-Hans": "匹配陪诊师",
      "en": "Matched Companions"
    },
    "matchedAt": {
      "zh-Hans": "匹配陪诊师 · {name}",
      "en": "Matched Companions · {name}",
      "_params": [
        "name"
      ]
    },
    "noMatchedCompanion": {
      "zh-Hans": "暂未找到匹配的陪诊师",
      "en": "No matched companions found"
    },
    "noRecommendCompanion": {
      "zh-Hans": "暂无推荐陪诊师，稍后再来看看",
      "en": "No recommendations yet. Check back later."
    },
    "loadMore": {
      "zh-Hans": "查看更多",
      "en": "Load More"
    },
    "allShown": {
      "zh-Hans": "— 已展示全部 —",
      "en": "— All shown —"
    },
    "selectCity": {
      "zh-Hans": "选择城市",
      "en": "Select City"
    },
    "autoLocate": {
      "zh-Hans": "自动定位",
      "en": "Auto Locate"
    },
    "availableCities": {
      "zh-Hans": "可选城市",
      "en": "Available Cities"
    }
  },
  "chat": {
    "title": {
      "zh-Hans": "聊天",
      "en": "Chat"
    },
    "inputPlaceholder": {
      "zh-Hans": "输入消息...",
      "en": "Type a message..."
    },
    "send": {
      "zh-Hans": "发送",
      "en": "Send"
    }
  },
  "city": {
    "locating": {
      "zh-Hans": "定位中...",
      "en": "Locating..."
    },
    "value": {
      "zh-Hans": "{city}",
      "en": "{city}",
      "_params": [
        "city"
      ],
      "_note": "无值时回退 common.notSet / Not Set"
    }
  },
  "price": {
    "amount": {
      "zh-Hans": "¥{amount}",
      "en": "¥{amount}",
      "_params": [
        "amount"
      ],
      "_note": "货币符号本期不本地化，保留 ¥ (PRD §7.5)"
    }
  },
  "hospital": {
    "searchPlaceholder": {
      "zh-Hans": "搜索医院名称",
      "en": "Search hospital name"
    }
  },
  "toast": {
    "locatedTo": {
      "zh-Hans": "已定位到 {city}",
      "en": "Located to {city}",
      "_params": [
        "city"
      ]
    },
    "locateFailed": {
      "zh-Hans": "定位失败",
      "en": "Location failed"
    },
    "locateFailedPerm": {
      "zh-Hans": "定位失败，请检查权限",
      "en": "Location failed, please check permissions"
    },
    "needLocationPerm": {
      "zh-Hans": "请允许位置权限",
      "en": "Please allow location access"
    },
    "selectedCity": {
      "zh-Hans": "已选择 {city}",
      "en": "Selected {city}",
      "_params": [
        "city"
      ]
    },
    "switching": {
      "zh-Hans": "切换中...",
      "en": "Switching..."
    },
    "switchFailed": {
      "zh-Hans": "切换失败",
      "en": "Switch failed"
    },
    "cleared": {
      "zh-Hans": "已清除",
      "en": "Cleared"
    },
    "agreeFirst": {
      "zh-Hans": "请先同意用户协议和隐私政策",
      "en": "Please agree to the User Agreement and Privacy Policy first"
    },
    "loginFailed": {
      "zh-Hans": "登录失败，请重试",
      "en": "Login failed, please try again"
    },
    "invalidPhone": {
      "zh-Hans": "请输入正确的手机号",
      "en": "Please enter a valid phone number"
    },
    "codeSent": {
      "zh-Hans": "验证码已发送",
      "en": "Verification code sent"
    },
    "sendFailed": {
      "zh-Hans": "发送失败，请重试",
      "en": "Failed to send, please try again"
    },
    "inputCode6": {
      "zh-Hans": "请输入6位验证码",
      "en": "Please enter the 6-digit code"
    },
    "codeWrongExpired": {
      "zh-Hans": "验证码错误或已过期",
      "en": "Code is incorrect or expired"
    },
    "opFailed": {
      "zh-Hans": "操作失败，请重试",
      "en": "Operation failed, please try again"
    },
    "selectHospitalFirst": {
      "zh-Hans": "请先选择医院",
      "en": "Please select a hospital first"
    },
    "selectServiceFirst": {
      "zh-Hans": "请先选择服务类型",
      "en": "Please select a service type first"
    },
    "selectCompanionFirst": {
      "zh-Hans": "请先选择陪诊师",
      "en": "Please select a companion first"
    }
  },
  "dialog": {
    "registerRoleTitle": {
      "zh-Hans": "注册新角色",
      "en": "Register New Role"
    },
    "registerRoleContent": {
      "zh-Hans": "您还没有{targetLabel}角色，是否前往注册？",
      "en": "You don't have the {targetLabel} role yet. Register now?",
      "_params": [
        "targetLabel"
      ]
    },
    "switchRoleTitle": {
      "zh-Hans": "切换角色",
      "en": "Switch Role"
    },
    "switchRoleContent": {
      "zh-Hans": "确定切换为{targetLabel}吗？",
      "en": "Switch to {targetLabel}?",
      "_params": [
        "targetLabel"
      ]
    },
    "tip": {
      "zh-Hans": "提示",
      "en": "Notice"
    },
    "clearCacheConfirm": {
      "zh-Hans": "确定清除缓存？",
      "en": "Clear cache?"
    }
  },
  "error": {
    "PHONE_REQUIRED": {
      "zh-Hans": "请先绑定手机号",
      "en": "Please bind your phone number first"
    },
    "REALNAME_REQUIRED": {
      "zh-Hans": "请先完成实名认证",
      "en": "Please complete real-name verification first",
      "_note": "reserved"
    },
    "VERIFICATION_PENDING": {
      "zh-Hans": "认证审核中，请稍候",
      "en": "Verification in progress, please wait",
      "_note": "reserved"
    },
    "VERIFICATION_REQUIRED": {
      "zh-Hans": "该操作需通过资质认证",
      "en": "This action requires verified qualification"
    },
    "PAYMENT_REQUIRED": {
      "zh-Hans": "请先完成支付",
      "en": "Please complete payment first"
    },
    "ORDER_HAS_UNPAID": {
      "zh-Hans": "存在未支付订单，请先处理",
      "en": "You have an unpaid order, please handle it first"
    },
    "ORDER_NOT_FOUND": {
      "zh-Hans": "订单不存在",
      "en": "Order not found"
    },
    "ORDER_TRANSITION_INVALID": {
      "zh-Hans": "订单状态不允许该操作",
      "en": "This action is not allowed in the current order status"
    },
    "SERVICE_PACKAGE_INVALID": {
      "zh-Hans": "所选服务档位不存在或已下架",
      "en": "The selected service package is unavailable"
    },
    "COMPANION_PROFILE_EXISTS": {
      "zh-Hans": "陪诊师资料已存在",
      "en": "Companion profile already exists"
    },
    "COMPANION_NOT_VERIFIED": {
      "zh-Hans": "陪诊师尚未通过认证",
      "en": "Companion is not yet verified"
    },
    "PAYMENT_REFUND_FAILED": {
      "zh-Hans": "退款失败，请稍后重试",
      "en": "Refund failed, please try again later"
    },
    "PAYMENT_PROVIDER_ERROR": {
      "zh-Hans": "支付渠道异常，请稍后重试",
      "en": "Payment provider error, please try again later"
    },
    "OTP_INVALID": {
      "zh-Hans": "验证码错误或已过期，请重新获取",
      "en": "Invalid or expired code, please request a new one"
    },
    "OTP_LOCKED": {
      "zh-Hans": "验证码尝试过多，请稍后再试",
      "en": "Too many attempts, please try again later"
    },
    "SMS_RATE_LIMITED": {
      "zh-Hans": "发送过于频繁，请稍后再试",
      "en": "Sending too frequently, please try again later"
    },
    "SHARE_F2_DISABLED": {
      "zh-Hans": "该功能暂时关闭",
      "en": "This feature is temporarily unavailable",
      "_note": "运营火度门"
    },
    "SHARE_SESSIONS_READONLY": {
      "zh-Hans": "当前为只读模式，暂不可操作",
      "en": "Read-only mode, action unavailable",
      "_note": "运营火度门"
    },
    "SHARE_F2_CANARY_NOT_WHITELISTED": {
      "zh-Hans": "该功能灰度测试中，暂未对您开放",
      "en": "This feature is in limited testing and not yet available to you",
      "_note": "灰度白名单门"
    }
  }
}
