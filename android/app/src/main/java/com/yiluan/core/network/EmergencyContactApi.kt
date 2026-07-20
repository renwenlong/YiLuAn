package com.yiluan.core.network

import com.yiluan.core.model.EmergencyContact
import com.yiluan.core.model.EmergencyContactRequest
import retrofit2.http.Body
import retrofit2.http.DELETE
import retrofit2.http.GET
import retrofit2.http.PUT
import retrofit2.http.POST
import retrofit2.http.Path

/**
 * 紧急联系人 API（需登录）。ANDROID-DEV-B6-LONGTAIL。
 * 注意: GET 返回裸 List（无 items/total wrapper）；更新用 PUT（非 PATCH）。
 */
interface EmergencyContactApi {
    @GET("emergency/contacts")
    suspend fun list(): List<EmergencyContact>

    @POST("emergency/contacts")
    suspend fun create(@Body body: EmergencyContactRequest): EmergencyContact

    @PUT("emergency/contacts/{contactId}")
    suspend fun update(
        @Path("contactId") contactId: String,
        @Body body: EmergencyContactRequest,
    ): EmergencyContact

    @DELETE("emergency/contacts/{contactId}")
    suspend fun delete(@Path("contactId") contactId: String)
}
