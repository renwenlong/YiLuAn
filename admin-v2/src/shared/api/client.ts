/**
 * Axios client (S2-DEV-013)
 * 每次 request 实时读 sessionStorage token（不缓存副本），acceptance #9
 */
import axios from 'axios'
import { getAdminToken } from './authStore'

export const apiClient = axios.create({
  baseURL: '/api/v1',  // dev proxy + nginx prod 反代 完全一致
  timeout: 10_000,
})

apiClient.interceptors.request.use((config) => {
  const token = getAdminToken()
  if (token) {
    // v1 admin-h5 用 header X-Admin-Token，v2 同源沿用
    config.headers.set('X-Admin-Token', token)
  }
  return config
})

apiClient.interceptors.response.use(
  (resp) => resp,
  (error) => {
    // 401 → token 失效，清掉同源 sessionStorage 触发 storage event 让其他 tab 同步
    if (error.response?.status === 401) {
      sessionStorage.removeItem('yiluan.admin.token')
      sessionStorage.removeItem('yiluan.admin.role')
      // 同时 reload 让 RequireAuth 跳 /login（避免本 tab 状态不一致）
      if (typeof window !== 'undefined') {
        window.location.assign('/admin-v2/login')
      }
    }
    return Promise.reject(error)
  },
)
