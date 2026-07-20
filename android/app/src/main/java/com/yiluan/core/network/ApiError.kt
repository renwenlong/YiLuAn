package com.yiluan.core.network

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.Json
import retrofit2.HttpException

/**
 * 后端统一错误体解析（对齐后端 error_code 语义）。
 * ANDROID-DEV-B3-COMPANION — 陪诊员接单前置门槛(PHONE_REQUIRED/VERIFICATION_REQUIRED)
 * 需按 error_code 区分引导，泛化 catch 不够。
 *
 * 后端错误体形如 {"detail": {"code": "PHONE_REQUIRED", "message": "..."}} 或
 * {"detail": "..."}（FastAPI 默认）。两种都尽力解析出 code。
 */
@Serializable
private data class ErrorEnvelope(
    @SerialName("detail") val detail: ErrorDetail? = null,
)

@Serializable
private data class ErrorDetail(
    @SerialName("code") val code: String? = null,
    @SerialName("message") val message: String? = null,
)

object ApiError {
    private val json = Json { ignoreUnknownKeys = true; coerceInputValues = true }

    /**
     * 从异常提取后端 error code（非 HttpException 或解析失败返回 null）。
     */
    fun codeOf(e: Throwable): String? {
        val http = e as? HttpException ?: return null
        val body = http.response()?.errorBody()?.string() ?: return null
        return try {
            json.decodeFromString<ErrorEnvelope>(body).detail?.code
        } catch (_: Exception) {
            null
        }
    }
}
