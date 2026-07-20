package com.yiluan.core.network

import com.yiluan.core.model.ApplyCompanionRequest
import com.yiluan.core.model.CompanionListResponse
import com.yiluan.core.model.CompanionProfile
import com.yiluan.core.model.CompanionStats
import com.yiluan.core.model.UpdateCompanionProfileRequest
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.POST
import retrofit2.http.PUT
import retrofit2.http.Path
import retrofit2.http.Query

/**
 * 陪诊员 API（需登录，走业务 Retrofit）。
 * ANDROID-DEV-B3-COMPANION — 入驻/档案/统计/公开详情/目录。
 *
 * 对齐后端 companions.py + iOS CompanionService。
 * 公开详情 GET /companions/{id} ABAC 脱敏；本人 GET /companions/me 含全字段。
 */
interface CompanionApi {
    /** 入驻申请（陪诊员资料提交），返回 pending 待审详情。 */
    @POST("companions/apply")
    suspend fun apply(@Body body: ApplyCompanionRequest): CompanionProfile

    /** 本人陪诊员详情（含 real_name + 全认证字段）。 */
    @GET("companions/me")
    suspend fun me(): CompanionProfile

    /** 更新本人档案（只传要改字段）。 */
    @PUT("companions/me")
    suspend fun updateMe(@Body body: UpdateCompanionProfileRequest): CompanionProfile

    /** 本人统计（接单数/评分/收入）。 */
    @GET("companions/me/stats")
    suspend fun myStats(): CompanionStats

    /** 公开陪诊员详情（患者视角，ABAC 脱敏）。 */
    @GET("companions/{companionId}")
    suspend fun detail(@Path("companionId") companionId: String): CompanionProfile

    /** 陪诊员目录（脱敏列表）。 */
    @GET("companions")
    suspend fun list(
        @Query("area") area: String?,
        @Query("city") city: String?,
        @Query("service_type") serviceType: String?,
        @Query("hospital_id") hospitalId: String?,
        @Query("page") page: Int,
        @Query("page_size") pageSize: Int,
    ): CompanionListResponse
}
