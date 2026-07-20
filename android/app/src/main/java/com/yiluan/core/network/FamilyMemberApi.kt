package com.yiluan.core.network

import com.yiluan.core.model.FamilyMemberListResponse
import com.yiluan.core.model.FamilyMemberProfile
import com.yiluan.core.model.FamilyMemberRequest
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PATCH
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * 家庭成员 API（需登录）。ANDROID-DEV-B6-LONGTAIL。
 * 注意: 更新用 PATCH（对齐后端 /users/me/family-members）。
 */
interface FamilyMemberApi {
    @GET("users/me/family-members")
    suspend fun list(): FamilyMemberListResponse

    @POST("users/me/family-members")
    suspend fun create(@Body body: FamilyMemberRequest): FamilyMemberProfile

    @PATCH("users/me/family-members/{memberId}")
    suspend fun update(
        @Path("memberId") memberId: String,
        @Body body: FamilyMemberRequest,
    ): FamilyMemberProfile

    @DELETE("users/me/family-members/{memberId}")
    suspend fun delete(@Path("memberId") memberId: String)
}
