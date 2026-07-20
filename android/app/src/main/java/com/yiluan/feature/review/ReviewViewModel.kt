package com.yiluan.feature.review

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.review.ReviewRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * 评价 ViewModel（写评价+评分）。
 * ANDROID-DEV-B6-LONGTAIL — ⚠️ 提交评价驱动订单 completed→reviewed（业务功能）。
 * 4 维度评分(1~5) + content(5~500 字)。
 */
@HiltViewModel
class ReviewViewModel @Inject constructor(
    private val repository: ReviewRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ReviewUiState())
    val uiState: StateFlow<ReviewUiState> = _uiState.asStateFlow()

    fun setPunctuality(v: Int) = _uiState.update { it.copy(punctuality = v.coerceIn(1, 5), error = null) }
    fun setProfessionalism(v: Int) = _uiState.update { it.copy(professionalism = v.coerceIn(1, 5), error = null) }
    fun setCommunication(v: Int) = _uiState.update { it.copy(communication = v.coerceIn(1, 5), error = null) }
    fun setAttitude(v: Int) = _uiState.update { it.copy(attitude = v.coerceIn(1, 5), error = null) }
    fun setContent(v: String) = _uiState.update { it.copy(content = v.take(500), error = null) }

    /** content 5~500 字且 4 维度都已评（默认 5，恒满足）。 */
    val canSubmit: Boolean
        get() = _uiState.value.content.length in 5..500

    fun submit(orderId: String, onSubmitted: () -> Unit) {
        val s = _uiState.value
        if (s.content.length !in 5..500) {
            _uiState.update { it.copy(error = ReviewErrorKey.CONTENT_INVALID) }
            return
        }
        if (s.isSubmitting) return
        _uiState.update { it.copy(isSubmitting = true, error = null) }
        viewModelScope.launch {
            try {
                repository.submitReview(
                    orderId = orderId,
                    punctuality = s.punctuality,
                    professionalism = s.professionalism,
                    communication = s.communication,
                    attitude = s.attitude,
                    content = s.content,
                )
                _uiState.update { it.copy(isSubmitting = false, submitted = true) }
                onSubmitted()
            } catch (e: Exception) {
                _uiState.update { it.copy(isSubmitting = false, error = ReviewErrorKey.SUBMIT_FAILED) }
            }
        }
    }

    fun clearError() = _uiState.update { it.copy(error = null) }
}

enum class ReviewErrorKey { CONTENT_INVALID, SUBMIT_FAILED }

data class ReviewUiState(
    val punctuality: Int = 5,
    val professionalism: Int = 5,
    val communication: Int = 5,
    val attitude: Int = 5,
    val content: String = "",
    val isSubmitting: Boolean = false,
    val submitted: Boolean = false,
    val error: ReviewErrorKey? = null,
)
