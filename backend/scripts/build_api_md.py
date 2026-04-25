"""Generate per-tag Markdown reference docs from openapi.json.

Run: python backend/scripts/build_api_md.py
Outputs: docs/api/<tag>.md and docs/api/README.md (regenerated).
"""
from __future__ import annotations

import collections
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCHEMA = ROOT / "docs" / "api" / "openapi.json"
OUT_DIR = ROOT / "docs" / "api"

# Static per-tag prose: 业务背景、鉴权、限流。
TAG_PROSE = {
    "auth": {
        "title": "认证（auth）",
        "intro": (
            "认证模块负责用户身份鉴别。提供两条登录链路：\n\n"
            "1. **手机号 + 短信验证码**（主要链路）：`/auth/send-otp` → `/auth/verify-otp` → 拿到 `access_token`。\n"
            "2. **微信小程序 code 登录**：`/auth/wechat-login`，必要时再补绑手机号。\n\n"
            "登录成功后，调用其他接口需要在请求头携带：\n\n"
            "```\nAuthorization: Bearer <access_token>\n```\n"
            "完整流程详见 [AUTHENTICATION.md](./AUTHENTICATION.md)。"
        ),
        "auth": "本模块各接口除 `/auth/bind-phone` 外**均不要求 Bearer Token**。",
        "rate_limit": "`/auth/send-otp` 限流 **5 次 / 分钟 / IP**。",
    },
    "users": {
        "title": "用户基础资料（users）",
        "intro": "用户账号本身的资料：昵称、头像、可用角色、活跃角色切换、注销。",
        "auth": "全部接口要求 `Authorization: Bearer <access_token>`。",
        "rate_limit": "无特殊限流，遵循全局默认。",
    },
    "patients": {
        "title": "患者档案（patients）",
        "intro": "患者档案补充医疗背景信息（紧急联系人、过敏史、常用医院），用于下单时自动填充。",
        "auth": "全部接口要求登录。",
        "rate_limit": "无特殊限流。",
    },
    "companions": {
        "title": "陪诊师档案（companions）",
        "intro": (
            "陪诊师入驻、资料维护、列表搜索、详情查看、个人统计。\n\n"
            "陪诊师身份生命周期：用户调用 `POST /companions/apply` → `pending` → 后台审核 → `verified` 即可接单。"
        ),
        "auth": "全部接口要求登录。`PUT /companions/me` 与 `/companions/me/stats` 还要求当前账号已开通陪诊师角色。",
        "rate_limit": "无特殊限流。",
    },
    "hospitals": {
        "title": "医院数据（hospitals）",
        "intro": "医院搜索、筛选项、按经纬度定位最近省市、详情查询。`POST /hospitals/seed` 仅用于初始化部署。",
        "auth": "搜索 / 详情接口**不强制登录**；`/hospitals/seed` 应通过运维通道执行。",
        "rate_limit": "列表查询带 1 小时 Redis 缓存，命中缓存不打 DB。",
    },
    "orders": {
        "title": "订单（orders）",
        "intro": (
            "订单贯穿『下单 → 支付 → 接单 → 服务 → 完成 / 退款』完整生命周期。常见状态：\n\n"
            "- `pending_payment` 待支付（30 分钟自动取消）\n"
            "- `paid` 已支付，等待陪诊师接单\n"
            "- `accepted` 已接单\n"
            "- `in_service` 服务中\n"
            "- `completed` 已完成\n"
            "- `cancelled_by_patient` / `cancelled_by_companion` / `rejected_by_companion` / `expired` 终态\n"
        ),
        "auth": "除 `/orders/check-expired`（`X-Admin-Token`）外，全部接口要求 `Authorization: Bearer <access_token>`，并强校验当前用户是否为订单参与方。",
        "rate_limit": "无特殊限流，遵循全局默认。",
    },
    "reviews": {
        "title": "订单评价（reviews）",
        "intro": "已完成订单的患者评价。**单订单仅可评价一次**。陪诊师详情页通过『陪诊师评价列表』展示历史评价。",
        "auth": "全部接口要求登录。提交评价仅订单的患者本人可调用。",
        "rate_limit": "无特殊限流。",
    },
    "chats": {
        "title": "订单聊天（chats）",
        "intro": (
            "订单参与方在订单生命周期内进行实时沟通。\n\n"
            "- 实时收发使用 `WS /api/v1/ws/chat/{order_id}?token=<jwt>`\n"
            "- HTTP 接口用于历史拉取、HTTP 兜底发送、批量已读"
        ),
        "auth": "全部接口要求登录，且当前用户必须是订单参与方（患者或接单陪诊师）。",
        "rate_limit": "WS 单条消息正文上限 4000 字符，HTTP 与之保持一致。",
    },
    "notifications": {
        "title": "站内通知（notifications）",
        "intro": "站内通知列表、未读数、标记已读、设备推送 token 注册/注销。推送通过 APNs / FCM / 微信订阅消息分发。",
        "auth": "全部接口要求登录。",
        "rate_limit": "无特殊限流。",
    },
    "wallet": {
        "title": "钱包（wallet）",
        "intro": "钱包余额、累计收入/支出、流水分页查询。提现走运营后台审核流，暂未对前端开放。",
        "auth": "全部接口要求登录。",
        "rate_limit": "无特殊限流。",
    },
    "payment-callbacks": {
        "title": "支付回调（payment-callbacks）",
        "intro": (
            "微信支付（含模拟 provider）回调入口。**这两个端点由微信服务端调用，并非前端 / App 调用。**\n\n"
            "幂等机制：`payment_callback_log` 唯一约束 `(provider, transaction_id)`。"
        ),
        "auth": "**不要求 JWT**。鉴权由微信回调签名验证完成。",
        "rate_limit": "无限流。微信侧 24 小时内最多 8 次重试，已通过幂等表去重。",
    },
    "admin": {
        "title": "运营后台 - 通用（admin）",
        "intro": "运营后台对订单、用户的管理操作（查询、强制状态、退款、停用/启用账号）。",
        "auth": "要求 `Authorization: Bearer <access_token>`，**且当前用户具备 `admin` 角色**（401 / 403 拦截）。",
        "rate_limit": "无特殊限流。",
    },
    "admin-companions": {
        "title": "运营后台 - 陪诊师审核（admin-companions）",
        "intro": "审核员审核陪诊师入驻申请：列表 / 批准 / 驳回（带原因）。",
        "auth": "**鉴权方式与其他接口不同**：请求头 `X-Admin-Token: <token>`，不使用 JWT。",
        "rate_limit": "无特殊限流。",
    },
    "health": {
        "title": "健康检查（health）",
        "intro": (
            "K8s / ACA 探针使用：\n\n"
            "- `GET /health`：liveness，进程存活即返回 200。\n"
            "- `GET /readiness` & `GET /api/v1/readiness`：检查 DB + Redis，全部 OK → 200，任一失败 → 503。\n"
            "- `GET /api/v1/ping`：通用连通性测试。"
        ),
        "auth": "无鉴权。",
        "rate_limit": "无限流。",
    },
}


def render_endpoint(method: str, path: str, op: dict) -> str:
    summary = op.get("summary", "").strip()
    description = op.get("description", "").strip()
    lines = [f"### `{method.upper()} {path}` — {summary}", "", description, ""]

    # parameters
    params = op.get("parameters") or []
    if params:
        lines.append("**参数：**")
        lines.append("")
        for p in params:
            loc = p.get("in")
            name = p.get("name")
            required = "✅" if p.get("required") else "—"
            schema = p.get("schema") or {}
            ptype = schema.get("type") or schema.get("$ref", "").rsplit("/", 1)[-1] or "—"
            desc = (p.get("description") or "").replace("\n", " ")
            lines.append(f"- `{name}` ({loc}, {ptype}, required={required}) — {desc}")
        lines.append("")

    # request body example
    rb = op.get("requestBody")
    if rb:
        content = (rb.get("content") or {}).get("application/json")
        if content and content.get("schema"):
            lines.append("**请求体（JSON）：**")
            lines.append("")
            lines.append("```json")
            lines.append(json.dumps(_example_for_schema(content["schema"]), ensure_ascii=False, indent=2))
            lines.append("```")
            lines.append("")

    # responses
    resps = op.get("responses") or {}
    if resps:
        lines.append("**响应：**")
        lines.append("")
        lines.append("| 状态码 | 说明 |")
        lines.append("| --- | --- |")
        for code in sorted(resps.keys(), key=lambda c: (len(c), c)):
            r = resps[code]
            d = (r.get("description") or "").replace("\n", " ").strip()
            lines.append(f"| `{code}` | {d} |")
        lines.append("")

    # curl example
    body_example = ""
    if rb:
        content = (rb.get("content") or {}).get("application/json") or {}
        ex = _example_for_schema(content.get("schema", {}))
        if ex:
            body_example = f" \\\n  -H 'Content-Type: application/json' \\\n  -d '{json.dumps(ex, ensure_ascii=False)}'"
    lines.append("**curl 示例：**")
    lines.append("")
    lines.append("```bash")
    lines.append(
        f"curl -X {method.upper()} 'https://api.yiluan.example.com{path}' \\\n"
        f"  -H 'Authorization: Bearer <access_token>'" + body_example
    )
    lines.append("```")
    lines.append("")
    return "\n".join(lines)


def _example_for_schema(schema: dict, depth: int = 0) -> object:
    if not isinstance(schema, dict) or depth > 4:
        return {}
    if "example" in schema:
        return schema["example"]
    if "examples" in schema and schema["examples"]:
        return schema["examples"][0]
    t = schema.get("type")
    if t == "object" or "properties" in schema:
        out = {}
        for k, v in (schema.get("properties") or {}).items():
            out[k] = _example_for_schema(v, depth + 1)
        return out
    if t == "array":
        return [_example_for_schema(schema.get("items") or {}, depth + 1)]
    if t == "integer":
        return 0
    if t == "number":
        return 0.0
    if t == "boolean":
        return True
    return ""


def main():
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    by_tag: dict[str, list] = collections.defaultdict(list)
    for path, methods in schema["paths"].items():
        for m, op in methods.items():
            if m.lower() not in {"get", "post", "put", "patch", "delete"}:
                continue
            for t in op.get("tags") or ["_untagged"]:
                by_tag[t].append((m, path, op))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # README index
    readme = ["# YiLuAn 后端 API 文档", "",
              "本文档由 `backend/scripts/dump_openapi.py` 与 `backend/scripts/build_api_md.py` 自动生成。",
              "源文件位于 `docs/api/openapi.json`，请勿手动编辑 `<tag>.md` 内的端点列表。",
              "",
              "## 通用文档", "",
              "- [认证流程（OTP / JWT / 微信登录）](./AUTHENTICATION.md)",
              "- [错误码与前端处理建议](./ERROR_HANDLING.md)",
              "- [openapi.json](./openapi.json) — 机读 OpenAPI 3 规范",
              "",
              "## 按业务模块索引",
              ""]
    for tag in sorted(by_tag, key=lambda t: list(TAG_PROSE).index(t) if t in TAG_PROSE else 999):
        prose = TAG_PROSE.get(tag, {"title": tag, "intro": ""})
        readme.append(f"### [{prose['title']}](./{tag}.md)")
        readme.append("")
        if prose.get("intro"):
            short = prose["intro"].split("\n\n")[0]
            readme.append(short)
            readme.append("")
        readme.append("| 方法 | 路径 | 说明 |")
        readme.append("| --- | --- | --- |")
        for m, path, op in sorted(by_tag[tag], key=lambda x: (x[1], x[0])):
            readme.append(f"| `{m.upper()}` | `{path}` | {(op.get('summary') or '').strip()} |")
        readme.append("")

    (OUT_DIR / "README.md").write_text("\n".join(readme), encoding="utf-8")

    # per-tag pages
    for tag, items in by_tag.items():
        prose = TAG_PROSE.get(tag, {"title": tag, "intro": "", "auth": "—", "rate_limit": "—"})
        page = [
            f"# {prose['title']}",
            "",
            "> 本文档由 OpenAPI schema 自动生成。如需修改端点说明，请编辑后端路由装饰器并重新生成。",
            "",
            "## 业务背景",
            "",
            prose.get("intro", "—"),
            "",
            "## 鉴权要求",
            "",
            prose.get("auth", "—"),
            "",
            "## 限流",
            "",
            prose.get("rate_limit", "—"),
            "",
            "## 端点速查",
            "",
            "| 方法 | 路径 | 说明 |",
            "| --- | --- | --- |",
        ]
        for m, path, op in sorted(items, key=lambda x: (x[1], x[0])):
            page.append(f"| `{m.upper()}` | `{path}` | {(op.get('summary') or '').strip()} |")
        page.append("")
        page.append("## 端点详情")
        page.append("")
        for m, path, op in sorted(items, key=lambda x: (x[1], x[0])):
            page.append(render_endpoint(m, path, op))
            page.append("---")
            page.append("")

        page.append("## 错误码对照")
        page.append("")
        page.append("通用错误码请见 [ERROR_HANDLING.md](./ERROR_HANDLING.md)。本模块在通用错误码之上的特殊语义：")
        page.append("")
        page.append("- `400 Bad Request`：业务规则不满足（如订单状态不允许该操作）。")
        page.append("- `401 Unauthorized`：未登录或令牌过期。")
        page.append("- `403 Forbidden`：已登录但无权访问该资源。")
        page.append("- `404 Not Found`：资源不存在。")
        page.append("- `422 Unprocessable Entity`：请求体字段校验失败（FastAPI 标准格式）。")
        page.append("- `429 Too Many Requests`：触发限流。")
        page.append("")
        (OUT_DIR / f"{tag}.md").write_text("\n".join(page), encoding="utf-8")

    print(f"OK: wrote README.md and {len(by_tag)} tag pages to {OUT_DIR}")


if __name__ == "__main__":
    main()
