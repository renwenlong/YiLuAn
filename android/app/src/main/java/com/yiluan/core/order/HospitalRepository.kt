package com.yiluan.core.order

import com.yiluan.core.model.Hospital
import com.yiluan.core.network.HospitalApi
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 医院仓库：create-order 选医院。
 * ANDROID-DEV-B2-PATIENT。
 */
@Singleton
class HospitalRepository @Inject constructor(
    private val hospitalApi: HospitalApi,
) {
    suspend fun searchHospitals(keyword: String? = null): List<Hospital> =
        hospitalApi.listHospitals(keyword = keyword?.takeIf { it.isNotBlank() }).items
}
