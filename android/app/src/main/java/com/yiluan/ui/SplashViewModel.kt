package com.yiluan.ui

import androidx.lifecycle.ViewModel
import com.yiluan.core.auth.AuthRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import javax.inject.Inject

/**
 * 启动屏 ViewModel：查本地是否已有 token 决定路由去向。
 * ANDROID-DEV-B1-AUTH。
 */
@HiltViewModel
class SplashViewModel @Inject constructor(
    private val repository: AuthRepository,
) : ViewModel() {
    suspend fun hasToken(): Boolean = repository.hasToken()
}
