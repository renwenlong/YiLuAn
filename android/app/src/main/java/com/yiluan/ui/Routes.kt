package com.yiluan.ui

/**
 * 导航路由定义（单一真源）。
 * ANDROID-DEV-B0-CORE — B0 只放骨架起始路由；各 Feature 路由在对应批次扩充，
 * 保持与 iOS 导航目标对齐。
 */
object Routes {
    const val SPLASH = "splash"
    // B1+ 扩充：LOGIN / ROLE_SELECT / PATIENT_HOME / COMPANION_HOME / ...

    /** 应用起始目的地（单一真源，供 NavHost 和测试共用）。 */
    const val START_DESTINATION = SPLASH
}
