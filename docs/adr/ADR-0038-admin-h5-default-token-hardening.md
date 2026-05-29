# ADR-0038: W19 P0-11 — admin-h5 默认 token 文案清除 + 临时硬化

- **状态**：Accepted（2026-05-28，魈）
- **范围**：W19 生产安全五件套之一，S 体量直接实施
- **关联**：ADR-0035 §3 P1-B；BACKLOG-ADMIN-V2（长期 admin-v2 重构是根治方案，本 ADR 仅 W19 创可贴）

---

## 1. 问题

`admin-h5/index.html:27` 明文展示：

```html
<!-- 类似 -->
<small>当前环境默认 Token: staging-admin-token</small>
```

- 凡能打开页面的人都能拿到一个能用的 token
- staging admin token 与生产共用 admin_jwt 验证路径（ADR-0034）；staging token 泄露不代表能直接进生产，但**心理安全感破坏 + 渗透测试 / 合规审计必报缺陷**

## 2. 修订决策

W19 不重构（admin-v2 是 P2 backlog），只做**最小硬化**：

### 2.1 删除明文 token 文案
- `admin-h5/index.html:27` 整段提示删掉
- 登录页保留输入框，不提供任何 token 示例 / 占位符 / "默认值" 文案
- 任何静态资源（README / help.html 等）grep `staging-admin-token` 全清

### 2.2 staging token 失效

- 后端 `core/admin_jwt.py` 维护 token revoke 列表（或直接旋转 staging signing key）
- 公司内 staging 使用者改为按需手动 issue 个人 token，TTL 8h
- 生产环境 admin token 必须强密码生成 + 强制 24h 轮换

### 2.3 admin-h5 加最小 CSP（已 TD-ADMIN-H5-CSP 处理过 token 存储 + nosniff，本次顺手加 CSP header）

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self' https://api.yiluan.cn;
```

不需要 hash / nonce（admin-h5 纯静态，inline script 已最小化）。

### 2.4 文档留痕

- `admin-h5/README.md` 顶部加一段 "本 admin-h5 为 MVP 创可贴版本，正式 admin-v2 见 BACKLOG-ADMIN-V2 / ADR-0034"
- `docs/adr/ADR-0034-admin-v2-auth.md` 末尾 follow-up 引用本 ADR

## 3. Acceptance（直接给胡桃 / 任意 frontend agent 实施 task）

1. ✅ `grep -r "staging-admin-token" admin-h5/` 返回空
2. ✅ `grep -r "默认 Token" admin-h5/` 返回空
3. ✅ staging admin signing key 已旋转 / 旧 staging token revoke 生效
4. ✅ admin-h5 响应 header 含 CSP（curl -I 验证）
5. ✅ admin-h5/README.md 含 admin-v2 长期化引用
6. ✅ 现有 admin 功能（陪诊师审核 MVP）回归正常

## 4. 实施提示

- 体量：~20 行 HTML 修改 + 后端 1 行 config + 部署侧 nginx CSP header
- 单测：admin 登录端到端 smoke（无 token 文案、CSP header 存在）
- 与其他 W19 task 互无依赖，可任意人插队 1 小时收口
- **不修不能上线**——属于发布前合规硬约束
