package com.yiluan.core.profile

import com.yiluan.core.model.BindPhoneRequest
import com.yiluan.core.model.CreateFollowupReminderRequest
import com.yiluan.core.model.EmergencyContact
import com.yiluan.core.model.EmergencyContactRequest
import com.yiluan.core.model.FamilyMemberProfile
import com.yiluan.core.model.FamilyMemberRequest
import com.yiluan.core.model.FollowupReminder
import com.yiluan.core.model.PaymentTransaction
import com.yiluan.core.model.User
import com.yiluan.core.model.WalletSummary
import com.yiluan.core.network.AuthApi
import com.yiluan.core.network.EmergencyContactApi
import com.yiluan.core.network.FamilyMemberApi
import com.yiluan.core.network.FollowupReminderApi
import com.yiluan.core.network.UserApi
import com.yiluan.core.network.WalletApi
import com.yiluan.core.storage.TokenStore
import javax.inject.Inject
import javax.inject.Singleton

/**
 * 个人中心仓库：家庭成员/紧急联系人/钱包/复诊提醒/绑手机/注销。
 * ANDROID-DEV-B6-LONGTAIL — 对齐 iOS Profile Feature。
 */
@Singleton
class ProfileRepository @Inject constructor(
    private val familyApi: FamilyMemberApi,
    private val emergencyApi: EmergencyContactApi,
    private val walletApi: WalletApi,
    private val followupApi: FollowupReminderApi,
    private val authApi: AuthApi,
    private val userApi: UserApi,
    private val tokenStore: TokenStore,
) {
    // 家庭成员
    suspend fun listFamilyMembers(): List<FamilyMemberProfile> = familyApi.list().items
    suspend fun createFamilyMember(req: FamilyMemberRequest): FamilyMemberProfile = familyApi.create(req)
    suspend fun updateFamilyMember(id: String, req: FamilyMemberRequest): FamilyMemberProfile =
        familyApi.update(id, req)
    suspend fun deleteFamilyMember(id: String) = familyApi.delete(id)

    // 紧急联系人
    suspend fun listEmergencyContacts(): List<EmergencyContact> = emergencyApi.list()
    suspend fun createEmergencyContact(req: EmergencyContactRequest): EmergencyContact =
        emergencyApi.create(req)
    suspend fun updateEmergencyContact(id: String, req: EmergencyContactRequest): EmergencyContact =
        emergencyApi.update(id, req)
    suspend fun deleteEmergencyContact(id: String) = emergencyApi.delete(id)

    // 钱包
    suspend fun walletSummary(): WalletSummary = walletApi.summary()
    suspend fun walletTransactions(page: Int = 1): List<PaymentTransaction> =
        walletApi.transactions(page = page, pageSize = 20).items

    // 复诊提醒
    suspend fun listFollowups(): List<FollowupReminder> = followupApi.list().items
    suspend fun createFollowup(orderId: String, req: CreateFollowupReminderRequest): FollowupReminder =
        followupApi.create(orderId, req)
    suspend fun deleteFollowup(reminderId: String) = followupApi.delete(reminderId)

    // 编辑资料
    /** 拉当前用户资料（用于编辑页回显）。 */
    suspend fun currentUser(): User = userApi.me()

    /** 更新资料（仅传要改的字段），返回更新后 User。 */
    suspend fun updateProfile(displayName: String?, avatarUrl: String?): User =
        userApi.updateMe(
            com.yiluan.core.model.UpdateMeRequest(
                displayName = displayName,
                avatarUrl = avatarUrl,
            ),
        )

    // 绑手机
    /** 向目标手机发验证码（绑定前）。 */
    suspend fun sendBindOtp(phone: String) {
        authApi.sendOtp(com.yiluan.core.model.SendOtpRequest(phone = phone))
    }

    suspend fun bindPhone(phone: String, code: String): User =
        authApi.bindPhone(BindPhoneRequest(phone = phone, code = code))

    /** 注销账户：删除后清本地 token。 */
    suspend fun deleteAccount() {
        userApi.deleteAccount()
        tokenStore.clear()
    }
}
