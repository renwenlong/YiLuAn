package com.yiluan.ui

/**
 * 导航路由定义（单一真源）。
 * ANDROID-DEV-B0-CORE — B0 骨架起始路由。
 * ANDROID-DEV-B1-AUTH — 加 login/role-select + home 占位。
 * ANDROID-DEV-B2-PATIENT — 加患者闭环: home/create-order/order-list/order-detail。
 */
object Routes {
    const val SPLASH = "splash"

    /** 认证流程（内部按 stage 切手机号/OTP/选角色）。 */
    const val AUTH = "auth"

    /** 登录后主界面（B2 起 = 患者首页）。 */
    const val HOME = "home"

    // ── B2 患者闭环 ──
    const val CREATE_ORDER = "create_order"
    const val ORDER_LIST = "order_list"

    /** 订单详情，带 orderId 参数。 */
    const val ORDER_DETAIL = "order_detail/{orderId}"
    fun orderDetail(orderId: String): String = "order_detail/$orderId"

    const val ARG_ORDER_ID = "orderId"

    // ── B6 长尾 ──
    const val SETTINGS = "settings"
    const val FAMILY_MEMBERS = "family_members"
    const val EMERGENCY_CONTACTS = "emergency_contacts"
    const val WALLET = "wallet"
    const val BIND_PHONE = "bind_phone"
    const val LEGAL_PRIVACY = "legal_privacy"
    const val LEGAL_TERMS = "legal_terms"

    /** 写评价，带 orderId。 */
    const val REVIEW = "review/{orderId}"
    fun review(orderId: String): String = "review/$orderId"

    /** 应用起始目的地（单一真源，供 NavHost 和测试共用）。 */
    const val START_DESTINATION = SPLASH
}
