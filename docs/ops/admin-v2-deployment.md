# admin-v2 部署文档（S2-DEV-013 PR-C）

> nginx /admin-v2/ 共存策略 + Vite build artifact 部署流程

---

## 前置

- S2-DEV-013 PR-A (#148) 已合 main → admin-v2/ 工程就位
- S2-DEV-013 PR-B (#149) 已合 main → backend 真接通
- S2-DEV-013 PR-C (本) 已合 main → nginx 路径分流就位

---

## 1. nginx 路径分流（共存）

| 路径 | 内容 | mount |
|---|---|---|
| `/api/v1/` | backend FastAPI | backend:8000 proxy |
| `/api/v1/ws/` | WebSocket | backend:8000 proxy |
| `/ws/` | WebSocket（旧） | backend:8000 proxy |
| `/admin/` | admin-h5 v1（vanilla JS）| `admin-h5/` |
| **`/admin-v2/`** | **admin-v2 React SPA dist** | **`admin-v2/dist/`** |
| `/__staging/mock-pay/` | mock pay stub | mock-pay-stub:8001 |
| `/__staging/mock-sms/` | mock sms stub | mock-sms-stub:8002 |
| `/health` `/readiness` | backend health | backend:8000 |

### admin-v2 SPA history fallback

```nginx
location /admin-v2/ {
    alias /usr/share/nginx/admin-v2/;
    index index.html;
    try_files $uri $uri/ /admin-v2/index.html;   # SPA: 未命中静态 → index.html
}
location ~* ^/admin-v2/.+\.(js|css|woff2?|png|jpg|svg|ico|map)$ {
    alias /usr/share/nginx/admin-v2/;
    add_header Cache-Control "public, max-age=31536000, immutable";   # 静态资源永久 cache
}
location = /admin-v2/index.html {
    add_header Cache-Control "no-store";   # index.html 无 cache 防版本漂移
}
```

---

## 2. 部署流程

### 2.1 dev（本地，无 nginx）

```bash
cd admin-v2
npm install
npm run dev
# → http://localhost:5173/admin-v2/  （Vite dev proxy /api/v1 → localhost:8000）
```

backend 单独起：
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

### 2.2 staging（nginx + dist mount）

**前置**：OPS 在主 tree（`~/repo/YiLuAn`）跑过 build：

```bash
cd ~/repo/YiLuAn/admin-v2
npm install
npm run build
# → admin-v2/dist/ 生成
```

然后起 staging 栈：

```bash
cd ~/repo/YiLuAn/deploy
./up.sh staging
# → http://127.0.0.1:18080/admin-v2/  （nginx mount admin-v2/dist）
# → http://127.0.0.1:18080/admin/      （admin-h5 v1 共存）
```

### 2.3 验证

```bash
# 1. nginx 路径分流正确
curl -sI http://127.0.0.1:18080/admin-v2/
# → 200，Content-Type: text/html

curl -sI http://127.0.0.1:18080/admin/
# → 200（v1 仍可用）

# 2. SPA history fallback
curl -sI http://127.0.0.1:18080/admin-v2/companion-review
# → 200（被 try_files fallback 到 index.html）

# 3. 静态资源 cache
curl -sI http://127.0.0.1:18080/admin-v2/assets/index-xxx.js
# → Cache-Control: public, max-age=31536000, immutable

# 4. 浏览器手动验证
# 打开 http://127.0.0.1:18080/admin-v2/
# 输入 admin token + 选角色 → 进 companion-review 页 → 看 list
```

---

## 3. v1 ↔ v2 共存验证

### 3.1 sessionStorage token 互认

- v2 登录后 → sessionStorage `yiluan.admin.token` 写入
- 同源跳 `/admin/` → v1 读 `yiluan.admin.token` → 不重新登录
- 反之亦然（v1 logout → 删 token → v2 通过 `storage` event 自动跳 login）

### 3.2 v1-only menu 项跳转

v2 menu 项点击：
- `companion-review` → React Router nav `/admin-v2/companion-review`
- `orders` / `users` / `audit` / `refund-review` / `dashboard` → tooltip + loading + `window.location.assign('/admin/#/<key>')` 整页跳 v1

---

## 4. CI artifact 部署（未来 OPS 自动化）

当前 PR-C：手动 build，OPS 负责。

未来升级：CI workflow `admin-v2-ci.yml` 已 upload-artifact `admin-v2-dist-${{ github.run_id }}`，OPS 可：
```bash
gh run download <run_id> -n admin-v2-dist-<run_id> -D admin-v2/dist
./up.sh staging
```

更未来：CI 构建 admin-v2-static Docker image push registry → docker-compose pull。属 OPS follow-up，不在 PR-C 范围。

---

## 5. 故障排查

| 现象 | 原因 | 修法 |
|---|---|---|
| `/admin-v2/` 404 | `admin-v2/dist/` 空 | `cd admin-v2 && npm install && npm run build` |
| nginx 启动报 `admin-v2/dist: no such file or directory` | 主 tree 没有 admin-v2/dist 占位 | 已加 `dist/.gitkeep` 保证目录存在 |
| `/admin-v2/anywhere` 返 nginx 404 不是 SPA index | nginx location 顺序/优先级 | 检查 `try_files $uri $uri/ /admin-v2/index.html` 在 location 内 |
| `/admin-v2/assets/*.js` 404 (静态资源取不到) | regex location + alias 拼出路径重复 | 本 PR 已修为 prefix location `/admin-v2/assets/`, 不走 regex 避免 path doubling |
| v2 调 API 401 | sessionStorage token 失效 / X-Admin-Token header 缺失 | 浏览器开 devtools 看 Network 请求 header；重登录 |
| v1↔v2 sessionStorage 同步失败 | 跨域 / 同源 storage event 未触发 | 确认两者同源 `127.0.0.1:18080`；不要直连 `localhost:18080` 跨主机 |

---

## 反向引用

- ADR-0042 admin-v2 框架选型 + B1 边界
- S2-DEV-013 task acceptance #7（nginx 共存）
- S2-TEST-009 admin-v2 冒烟（A-5 sessionStorage 互认 / A-1~4 v1↔v2 跳转）
- `admin-v2/README.md` 工程结构
- `deploy/nginx/nginx.conf` location 配置
- `deploy/docker-compose.yml` nginx mount
