package com.yiluan.feature.profile

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.yiluan.core.model.EmergencyContact
import com.yiluan.core.model.EmergencyContactRequest
import com.yiluan.core.model.FamilyMemberProfile
import com.yiluan.core.model.FamilyMemberRequest
import com.yiluan.core.model.FollowupReminder
import com.yiluan.core.model.PaymentTransaction
import com.yiluan.core.model.User
import com.yiluan.core.model.WalletSummary
import com.yiluan.core.profile.ProfileRepository
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import javax.inject.Inject

/**
 * 个人中心 ViewModel：家庭成员/紧急联系人/钱包/绑手机/注销。
 * ANDROID-DEV-B6-LONGTAIL — 对齐 iOS Profile Feature。
 */
@HiltViewModel
class ProfileViewModel @Inject constructor(
    private val repository: ProfileRepository,
) : ViewModel() {

    private val _uiState = MutableStateFlow(ProfileUiState())
    val uiState: StateFlow<ProfileUiState> = _uiState.asStateFlow()

    // MARK: - 家庭成员

    fun loadFamilyMembers() {
        _uiState.update { it.copy(isLoadingFamily = true) }
        viewModelScope.launch {
            try {
                val list = repository.listFamilyMembers()
                _uiState.update { it.copy(isLoadingFamily = false, familyMembers = list) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingFamily = false, error = ProfileErrorKey.LOAD_FAILED) }
            }
        }
    }

    fun addFamilyMember(name: String, relation: String, phone: String?) {
        if (name.isBlank() || name.length > 50) {
            _uiState.update { it.copy(error = ProfileErrorKey.INVALID_INPUT) }
            return
        }
        _uiState.update { it.copy(isMutating = true, error = null) }
        viewModelScope.launch {
            try {
                repository.createFamilyMember(
                    FamilyMemberRequest(name = name, relation = relation, phone = phone?.takeIf { it.isNotBlank() }),
                )
                _uiState.update { it.copy(isMutating = false) }
                loadFamilyMembers()
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ProfileErrorKey.SAVE_FAILED) }
            }
        }
    }

    fun deleteFamilyMember(id: String) {
        viewModelScope.launch {
            try {
                repository.deleteFamilyMember(id)
                loadFamilyMembers()
            } catch (e: Exception) {
                _uiState.update { it.copy(error = ProfileErrorKey.SAVE_FAILED) }
            }
        }
    }

    // MARK: - 紧急联系人

    fun loadEmergencyContacts() {
        _uiState.update { it.copy(isLoadingEmergency = true) }
        viewModelScope.launch {
            try {
                val list = repository.listEmergencyContacts()
                _uiState.update { it.copy(isLoadingEmergency = false, emergencyContacts = list) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingEmergency = false, error = ProfileErrorKey.LOAD_FAILED) }
            }
        }
    }

    fun addEmergencyContact(name: String, phone: String, relationship: String?) {
        if (name.isBlank() || !PHONE_REGEX.matches(phone)) {
            _uiState.update { it.copy(error = ProfileErrorKey.INVALID_INPUT) }
            return
        }
        _uiState.update { it.copy(isMutating = true, error = null) }
        viewModelScope.launch {
            try {
                repository.createEmergencyContact(
                    EmergencyContactRequest(name = name, phone = phone, relationship = relationship?.takeIf { it.isNotBlank() }),
                )
                _uiState.update { it.copy(isMutating = false) }
                loadEmergencyContacts()
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ProfileErrorKey.SAVE_FAILED) }
            }
        }
    }

    fun deleteEmergencyContact(id: String) {
        viewModelScope.launch {
            try {
                repository.deleteEmergencyContact(id)
                loadEmergencyContacts()
            } catch (e: Exception) {
                _uiState.update { it.copy(error = ProfileErrorKey.SAVE_FAILED) }
            }
        }
    }

    // MARK: - 复诊提醒

    /** 拉取当前用户的复诊提醒列表。 */
    fun loadFollowups() {
        _uiState.update { it.copy(isLoadingFollowups = true) }
        viewModelScope.launch {
            try {
                val list = repository.listFollowups()
                _uiState.update { it.copy(isLoadingFollowups = false, followups = list) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingFollowups = false, error = ProfileErrorKey.LOAD_FAILED) }
            }
        }
    }

    /** 删除一条复诊提醒(仅 pending 可删)，成功后重拉。 */
    fun deleteFollowup(id: String) {
        viewModelScope.launch {
            try {
                repository.deleteFollowup(id)
                loadFollowups()
            } catch (e: Exception) {
                _uiState.update { it.copy(error = ProfileErrorKey.SAVE_FAILED) }
            }
        }
    }

    // MARK: - 编辑资料

    /** 拉当前资料回显编辑页。 */
    fun loadProfile() {
        _uiState.update { it.copy(isLoadingProfile = true) }
        viewModelScope.launch {
            try {
                val user = repository.currentUser()
                _uiState.update { it.copy(isLoadingProfile = false, profile = user) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingProfile = false, error = ProfileErrorKey.LOAD_FAILED) }
            }
        }
    }

    /** 保存资料（昵称/头像），成功后刷新 profile + 置 profileSaved。 */
    fun saveProfile(displayName: String, avatarUrl: String?) {
        if (displayName.isBlank() || displayName.length > 50) {
            _uiState.update { it.copy(error = ProfileErrorKey.INVALID_INPUT) }
            return
        }
        _uiState.update { it.copy(isMutating = true, error = null, profileSaved = false) }
        viewModelScope.launch {
            try {
                val updated = repository.updateProfile(
                    displayName = displayName,
                    avatarUrl = avatarUrl?.takeIf { it.isNotBlank() },
                )
                _uiState.update { it.copy(isMutating = false, profile = updated, profileSaved = true) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ProfileErrorKey.SAVE_FAILED) }
            }
        }
    }

    // MARK: - 钱包

    fun loadWallet() {
        _uiState.update { it.copy(isLoadingWallet = true) }
        viewModelScope.launch {
            try {
                val summary = repository.walletSummary()
                val txns = repository.walletTransactions()
                _uiState.update { it.copy(isLoadingWallet = false, wallet = summary, transactions = txns) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isLoadingWallet = false, error = ProfileErrorKey.LOAD_FAILED) }
            }
        }
    }

    // MARK: - 绑手机

    /** 发绑定验证码到目标手机。 */
    fun sendBindOtp(phone: String) {
        if (!PHONE_REGEX.matches(phone)) {
            _uiState.update { it.copy(error = ProfileErrorKey.INVALID_INPUT) }
            return
        }
        _uiState.update { it.copy(isMutating = true, error = null) }
        viewModelScope.launch {
            try {
                repository.sendBindOtp(phone)
                _uiState.update { it.copy(isMutating = false, bindOtpSent = true) }
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ProfileErrorKey.BIND_FAILED) }
            }
        }
    }

    fun bindPhone(phone: String, code: String, onSuccess: () -> Unit) {
        if (!PHONE_REGEX.matches(phone) || !CODE_REGEX.matches(code)) {
            _uiState.update { it.copy(error = ProfileErrorKey.INVALID_INPUT) }
            return
        }
        _uiState.update { it.copy(isMutating = true, error = null) }
        viewModelScope.launch {
            try {
                repository.bindPhone(phone, code)
                _uiState.update { it.copy(isMutating = false) }
                onSuccess()
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ProfileErrorKey.BIND_FAILED) }
            }
        }
    }

    // MARK: - 注销（二次确认后调用）

    fun deleteAccount(onDeleted: () -> Unit) {
        _uiState.update { it.copy(isMutating = true, error = null) }
        viewModelScope.launch {
            try {
                repository.deleteAccount()
                _uiState.update { it.copy(isMutating = false) }
                onDeleted()
            } catch (e: Exception) {
                _uiState.update { it.copy(isMutating = false, error = ProfileErrorKey.DELETE_FAILED) }
            }
        }
    }

    fun clearError() = _uiState.update { it.copy(error = null) }

    private companion object {
        val PHONE_REGEX = Regex("^1[3-9]\\d{9}$")
        val CODE_REGEX = Regex("^\\d{6}$")
    }
}

/** 个人中心错误 key。 */
enum class ProfileErrorKey {
    LOAD_FAILED, SAVE_FAILED, INVALID_INPUT, BIND_FAILED, DELETE_FAILED
}

/** 个人中心 UI 状态。 */
data class ProfileUiState(
    val familyMembers: List<FamilyMemberProfile> = emptyList(),
    val isLoadingFamily: Boolean = false,
    val emergencyContacts: List<EmergencyContact> = emptyList(),
    val isLoadingEmergency: Boolean = false,
    val wallet: WalletSummary? = null,
    val transactions: List<PaymentTransaction> = emptyList(),
    val isLoadingWallet: Boolean = false,
    val followups: List<FollowupReminder> = emptyList(),
    val isLoadingFollowups: Boolean = false,
    val profile: User? = null,
    val isLoadingProfile: Boolean = false,
    val profileSaved: Boolean = false,
    val bindOtpSent: Boolean = false,
    val isMutating: Boolean = false,
    val error: ProfileErrorKey? = null,
)
