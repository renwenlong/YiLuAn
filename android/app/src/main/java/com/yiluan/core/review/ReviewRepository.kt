package com.yiluan.core.review

import com.yiluan.core.model.CreateReviewRequest
import com.yiluan.core.model.ReviewResponse
import com.yiluan.core.network.ReviewApi
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 评价仓库：提交/查询评价。
 * ANDROID-DEV-B6-LONGTAIL — ⚠️ 提交评价驱动订单 completed→reviewed（业务功能）。
 */
@Singleton
class ReviewRepository @Inject constructor(
    private val reviewApi: ReviewApi,
) {
    /**
     * 提交多维度评价（4 维度 + content 5~500 字）。成功后订单变 reviewed。
     */
    suspend fun submitReview(
        orderId: String,
        punctuality: Int,
        professionalism: Int,
        communication: Int,
        attitude: Int,
        content: String,
    ): ReviewResponse = reviewApi.submit(
        orderId,
        CreateReviewRequest(
            punctualityRating = punctuality,
            professionalismRating = professionalism,
            communicationRating = communication,
            attitudeRating = attitude,
            content = content,
        ),
    )

    suspend fun getReview(orderId: String): ReviewResponse = reviewApi.getReview(orderId)
}
