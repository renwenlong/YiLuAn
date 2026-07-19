package com.yiluan.feature.order

import androidx.annotation.StringRes
import com.yiluan.R
import com.yiluan.core.model.OrderStatus

/**
 * 订单状态 → i18n string res 映射（UI 层统一，不在 model 拼文案）。
 * ANDROID-DEV-B2-PATIENT。
 */
@StringRes
fun orderStatusLabel(status: String): Int = when (OrderStatus.fromValue(status)) {
    OrderStatus.CREATED -> R.string.order_status_created
    OrderStatus.ACCEPTED -> R.string.order_status_accepted
    OrderStatus.IN_PROGRESS -> R.string.order_status_in_progress
    OrderStatus.COMPLETED -> R.string.order_status_completed
    OrderStatus.REVIEWED -> R.string.order_status_reviewed
    OrderStatus.CANCELLED_BY_PATIENT -> R.string.order_status_cancelled_by_patient
    OrderStatus.CANCELLED_BY_COMPANION -> R.string.order_status_cancelled_by_companion
    OrderStatus.REJECTED_BY_COMPANION -> R.string.order_status_rejected_by_companion
    OrderStatus.EXPIRED -> R.string.order_status_expired
    null -> R.string.order_status_unknown
}
