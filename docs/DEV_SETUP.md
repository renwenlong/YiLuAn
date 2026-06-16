# Local / Staging Setup

本仓库默认后端环境是 **staging**。本地联调、微信开发者工具、admin H5 都走 staging docker 栈。

```bash
cd deploy
./up.sh            # 等同 ./up.sh staging，自动叠加 env.staging.local（若存在）
```

关键地址：

- API: `http://127.0.0.1:18080/api/v1`
- Health: `http://127.0.0.1:18080/health`
- Admin H5: `http://127.0.0.1:18080/admin/`

登录说明：

- 微信登录使用微信开发者工具返回的真实 `wx.login` code。
- staging 后端必须通过 `deploy/env.staging.local` 注入真实 `WECHAT_APP_ID` / `WECHAT_APP_SECRET`。
- OTP 不再有万能码；mock SMS 路径会把随机 OTP 写入 Redis，测试 helper 读取该值。
