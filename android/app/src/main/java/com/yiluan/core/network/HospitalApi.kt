package com.yiluan.core.network

import com.yiluan.core.model.HospitalListResponse
import retrofit2.http.GET
import retrofit2.http.Query

/**
 * 医院 API（需登录，走业务 Retrofit）。
 * ANDROID-DEV-B2-PATIENT — create-order 选医院。
 *
 * 对齐后端 hospitals.py（Redis 缓存 1h）+ iOS HospitalService。
 * B2 最简用 keyword 搜索；province/city 等级联过滤字段预留。
 */
interface HospitalApi {
    @GET("hospitals")
    suspend fun listHospitals(
        @Query("keyword") keyword: String?,
        @Query("province") province: String?,
        @Query("city") city: String?,
        @Query("page") page: Int,
        @Query("page_size") pageSize: Int,
    ): HospitalListResponse
}
