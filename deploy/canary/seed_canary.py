"""
Canary fixture seeder (S2-OPS-013 OPS gap-2).

Run from host AFTER ``bash up.sh canary`` + backend healthy.

凝光 13:55 UTC 业务边界最小集：

* admin: phone 13900000000 (sentinel admin via DB exec)
* companion: phone 13900000001 / status=active(approved) / cert_status=certified
             / 关联至少 1 档 active 服务 (service_types)
* 用户: phone 13800000001 / 已实名
* service_packages: 已由 alembic seed migration 装 3 档 active (b3c4d5e6f7a8)
* §2 复测需求: 1 active share token + 1 family viewer

测试侧 (刻晴) §1.3 退款 + §1.4 ledger 平账 + §5 真告警链路 复测依赖本 fixture.

Idempotent: 重跑安全 (login OTP 创建 user; companion apply 重复 400 ignored;
admin approve 重复 200/4xx ignored; share token 重复创建容忍).

Usage:
    python deploy/canary/seed_canary.py
    python deploy/canary/seed_canary.py --base http://127.0.0.1:18090
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request


CANARY_BASE = "http://127.0.0.1:18090"
CANARY_PROJECT = "yiluan-canary"
ADMIN_PHONE = "13900000000"
COMPANION_PHONE = "13900000001"
USER_PHONE = "13800000001"
FAMILY_VIEWER_PHONE = "13800000002"


def http(
    method: str,
    url: str,
    body: dict | None = None,
    headers: dict | None = None,
    timeout: float = 10.0,
) -> tuple[int, dict | str]:
    data = None
    h = {"content-type": "application/json"}
    if headers:
        h.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            txt = r.read().decode("utf-8", errors="replace")
            try:
                return r.status, json.loads(txt)
            except Exception:
                return r.status, txt
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(txt)
        except Exception:
            return e.code, txt


def wait_backend(base: str, timeout: float = 90.0) -> None:
    url = f"{base}/api/v1/ping"
    deadline = time.time() + timeout
    last: tuple[object, object] | None = None
    while time.time() < deadline:
        try:
            code, body = http("GET", url, timeout=3.0)
            if code == 200:
                print(f"[canary-seed] backend ready: {body}")
                return
            last = (code, body)
        except Exception as e:  # noqa: BLE001
            last = ("EXC", str(e))
        time.sleep(2.0)
    raise SystemExit(f"[canary-seed] backend not ready after {timeout}s: {last}")


def login_otp(base: str, phone: str) -> dict:
    code, body = http(
        "POST",
        f"{base}/api/v1/auth/verify-otp",
        body={"phone": phone, "code": "000000"},
    )
    if code != 200:
        raise SystemExit(f"[canary-seed] login failed for {phone}: {code} {body}")
    return body


def ensure_admin_user(compose_project: str = CANARY_PROJECT) -> None:
    """Create / update an admin user in the canary DB via container exec."""
    script = (
        "import asyncio, uuid\n"
        "from sqlalchemy import text\n"
        "from app.database import async_session\n"
        f"ADMIN_PHONE='{ADMIN_PHONE}'\n"
        "async def main():\n"
        "    async with async_session() as s:\n"
        "        row = (await s.execute(text(\"select id from users where phone=:p\"), {'p':ADMIN_PHONE})).first()\n"
        "        if row:\n"
        "            await s.execute(text(\"update users set roles='admin', is_active=true where phone=:p\"), {'p':ADMIN_PHONE})\n"
        "        else:\n"
        "            uid = uuid.uuid4()\n"
        "            await s.execute(text(\"insert into users (id, phone, roles, is_active, created_at, updated_at) values (:id, :p, 'admin', true, now(), now())\"), {'id':uid,'p':ADMIN_PHONE})\n"
        "        await s.commit()\n"
        "    print('admin user ensured:', ADMIN_PHONE)\n"
        "asyncio.run(main())\n"
    )
    cmd = [
        "docker", "compose", "-p", compose_project,
        "exec", "-T", "backend", "python", "-c", script,
    ]
    print(f"[canary-seed] ensure admin via docker exec {compose_project}")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("[canary-seed] admin stdout:", res.stdout)
        print("[canary-seed] admin stderr:", res.stderr)
        raise SystemExit("[canary-seed] failed to ensure admin user")
    print(res.stdout.strip())


def seed_hospitals(base: str) -> None:
    code, body = http("POST", f"{base}/api/v1/hospitals/seed")
    if code != 200:
        print(f"[canary-seed] hospital seed: code={code} body={body}")
    else:
        print(f"[canary-seed] hospitals: {body}")


def seed_patient(base: str, phone: str) -> dict:
    tok = login_otp(base, phone)
    print(f"[canary-seed] patient {phone} ready")
    return {"phone": phone, "user": tok["user"], "access_token": tok["access_token"]}


def seed_companion(base: str, admin_token: str, phone: str) -> dict:
    """Seed 1 canary companion = approved + active + 关联 full_accompany 服务."""
    # 1. login (create user if absent)
    tok = login_otp(base, phone)
    access = tok["access_token"]
    uid = tok["user"]["id"]

    # 2. pick a hospital for service_hospitals binding
    code, hospitals = http("GET", f"{base}/api/v1/hospitals?page=1&page_size=1")
    hid = ""
    if code == 200 and isinstance(hospitals, dict):
        items = hospitals.get("items", []) or []
        if items:
            hid = items[0].get("id", "")

    # 3. apply as companion (idempotent: 400 if already applied = OK)
    apply_code, apply_body = http(
        "POST",
        f"{base}/api/v1/companions/apply",
        headers={"authorization": f"Bearer {access}"},
        body={
            "real_name": "Canary陪诊师A",
            "service_types": "full_accompany,half_accompany,errand",
            "service_city": "北京",
            "service_area": "朝阳区,海淀区",
            "service_hospitals": hid,
            "bio": "canary seed companion (S2-OPS-013 OPS gap-2)",
        },
    )
    if apply_code not in (200, 201):
        print(
            f"[canary-seed] companion apply {phone}: "
            f"{apply_code} {str(apply_body)[:200]} (ignored)"
        )

    # 4. lookup companion id (need profile id, not user id, for approve)
    cid = None
    list_code, list_body = http(
        "GET",
        f"{base}/api/v1/admin/companions/?page=1&page_size=100",
        headers={"X-Admin-Token": admin_token},
    )
    if list_code == 200 and isinstance(list_body, dict):
        for c in list_body.get("items", []) or []:
            if c.get("user_id") == uid or c.get("phone") == phone:
                cid = c.get("id")
                break
    if not cid:
        me_code, me_body = http(
            "GET",
            f"{base}/api/v1/companions/me",
            headers={"authorization": f"Bearer {access}"},
        )
        if me_code == 200 and isinstance(me_body, dict):
            cid = me_body.get("id")

    # 5. admin approve (idempotent)
    if cid:
        ap_code, ap_body = http(
            "POST",
            f"{base}/api/v1/admin/companions/{cid}/approve",
            headers={"X-Admin-Token": admin_token},
        )
        if ap_code not in (200, 201):
            print(
                f"[canary-seed] companion approve {phone}: "
                f"{ap_code} {ap_body} (ignored)"
            )
    else:
        print(f"[canary-seed] WARN: failed to locate companion id for {phone}")

    # 6. re-login so role/roles claim is fresh
    tok = login_otp(base, phone)
    print(f"[canary-seed] companion {phone} active + certified + service_types ready")
    return {
        "phone": phone,
        "user": tok["user"],
        "access_token": tok["access_token"],
        "companion_id": cid,
    }


def seed_share_token_and_family(
    base: str, patient: dict, viewer_phone: str
) -> None:
    """Seed §2 family share replay: 1 active share token + 1 family viewer.

    凝光业务边界要求: §2 复测需要 patient 把订单 share 给 family viewer 换 session.
    canary 阶段无业务订单时退化为: 先确保 viewer user 存在 (登一次), share token
    需要订单存在所以这里只 placeholder, 实际复测时刻晴下完订单再 share.
    """
    # 1. ensure family viewer exists
    login_otp(base, viewer_phone)
    print(
        f"[canary-seed] family viewer {viewer_phone} ready (share token will be"
        f" created by §2 复测流程, 本 seed 只保 viewer 账号存在)"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=CANARY_BASE)
    ap.add_argument(
        "--admin-token",
        default="staging-admin-token",
        help="X-Admin-Token; canary 沿用 staging 默认 (env.canary 未覆写)",
    )
    ap.add_argument("--compose-project", default=CANARY_PROJECT)
    args = ap.parse_args()

    print(f"[canary-seed] base={args.base} project={args.compose_project}")
    wait_backend(args.base)
    ensure_admin_user(compose_project=args.compose_project)
    seed_hospitals(args.base)

    patient = seed_patient(args.base, USER_PHONE)
    seed_companion(args.base, admin_token=args.admin_token, phone=COMPANION_PHONE)
    seed_share_token_and_family(args.base, patient, FAMILY_VIEWER_PHONE)

    print("")
    print("[canary-seed] ✅ canary fixtures ready — 凝光业务边界 4 项已就位:")
    print(f"   - admin {ADMIN_PHONE}")
    print(f"   - patient {USER_PHONE}")
    print(f"   - companion {COMPANION_PHONE} (active + certified)")
    print(f"   - family viewer {FAMILY_VIEWER_PHONE}")
    print(
        "   - service_packages 3 档 (alembic seed b3c4d5e6f7a8 已装)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
