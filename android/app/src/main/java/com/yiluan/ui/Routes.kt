package com.yiluan.ui

/**
 * 导航路由定义（单一真源）。
 * ANDROID-DEV-B0-CORE — B0 只放骨架起始路由。
 * ANDROID-DEV-B1-AUTH — 加 login / role-select（含在 AuthScreen 内切换）+ home 占位。
 * 各 Feature 路由在对应批次扩充，保持与 iOS 导航目标对齐。
 */
object Routes {
    const val SPLASH = "splash"

    /** 认证流程（内部按 stage 切手机号/OTP/选角色，对齐 iOS AuthView）。 */
    const val AUTH = "auth"

    /** 登录完成后的主界面占位（患者/陪诊员真实 home 在 B2/B3 落地）。 */
    const val HOME = "home"

    /** 应用起始目的地（单一真源，供 NavHost 和测试共用）。 */
    const val START_DESTINATION = SPLASH
}
