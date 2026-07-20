package com.yiluan.core.companion

import com.yiluan.core.model.ApplyCompanionRequest
import com.yiluan.core.model.CompanionProfile
import com.yiluan.core.model.CompanionStats
import com.yiluan.core.model.UpdateCompanionProfileRequest
import com.yiluan.core.network.CompanionApi
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 陪诊员仓库：入驻/档案/统计/公开详情。
 * ANDROID-DEV-B3-COMPANION — 对齐 iOS CompanionService。
 */
@Singleton
class CompanionRepository @Inject constructor(
    private val companionApi: CompanionApi,
) {
    suspend fun apply(request: ApplyCompanionRequest): CompanionProfile =
        companionApi.apply(request)

    suspend fun myProfile(): CompanionProfile = companionApi.me()

    suspend fun updateProfile(request: UpdateCompanionProfileRequest): CompanionProfile =
        companionApi.updateMe(request)

    suspend fun myStats(): CompanionStats = companionApi.myStats()

    suspend fun companionDetail(companionId: String): CompanionProfile =
        companionApi.detail(companionId)

    suspend fun searchCompanions(
        city: String? = null,
        serviceType: String? = null,
    ): List<com.yiluan.core.model.CompanionDirectoryItem> =
        companionApi.list(
            area = null,
            city = city,
            serviceType = serviceType,
            hospitalId = null,
            page = 1,
            pageSize = 20,
        ).items
}
