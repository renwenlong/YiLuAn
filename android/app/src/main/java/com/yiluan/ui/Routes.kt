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

    // ── B4 实时 ──
    const val CHAT_LIST = "chat_list"
    const val NOTIFICATIONS = "notifications"

    /** 聊天室，带 orderId。 */
    const val CHAT_ROOM = "chat_room/{orderId}"
    fun chatRoom(orderId: String): String = "chat_room/$orderId"

    // ── B6 长尾 ──
    const val SETTINGS = "settings"
    const val FAMILY_MEMBERS = "family_members"
    const val EMERGENCY_CONTACTS = "emergency_contacts"
    const val WALLET = "wallet"
    const val FOLLOWUP_REMINDERS = "followup_reminders"
    const val BIND_PHONE = "bind_phone"
    const val LEGAL_PRIVACY = "legal_privacy"
    const val LEGAL_TERMS = "legal_terms"

    /** 写评价，带 orderId。 */
    const val REVIEW = "review/{orderId}"
    fun review(orderId: String): String = "review/$orderId"

    // ── B3 陆诊员闭环 ──
    const val COMPANION_HOME = "companion_home"
    const val COMPANION_AVAILABLE = "companion_available"
    const val COMPANION_TODAY = "companion_today"
    const val COMPANION_SETUP = "companion_setup"
    const val COMPANION_PROFILE = "companion_profile"

    /** 陆诊员详情（患者视角），带 companionId。 */
    const val COMPANION_DETAIL = "companion_detail/{companionId}"
    fun companionDetail(companionId: String): String = "companion_detail/$companionId"
    const val ARG_COMPANION_ID = "companionId"

    // ── B5 Precheck + Share ──
    const val PRECHECK = "precheck/{orderId}"
    fun precheck(orderId: String): String = "precheck/$orderId"
    const val SHARE_MANAGE = "share_manage/{orderId}"
    fun shareManage(orderId: String): String = "share_manage/$orderId"
    const val SHARE_OTP = "share_otp/{token}"
    fun shareOtp(token: String): String = "share_otp/$token"
    const val ARG_TOKEN = "token"

    /** 应用起始目的地（单一真源，供 NavHost 和测试共用）。 */
    const val START_DESTINATION = SPLASH
}
