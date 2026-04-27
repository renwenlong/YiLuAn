"""
Staging fixture seeder (D-044).

Run from host AFTER docker compose up + backend healthy.

Seeds:
  * 1 admin user (created via DB exec; phone 13900000000, role=admin)
  * 5 patients (registered via OTP login, phone 13800000001..05)
  * 3 companions (registered + applied + admin-approved,
                  phone 13800000101..103)
  * Hospitals seeded via /api/v1/hospitals/seed

Idempotent: re-running is safe (uses ON CONFLICT for admin row,
the API endpoints already short-circuit on existing rows).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error


def http(method: str, url: str, body: dict | None = None,
         headers: dict | None = None, timeout: float = 10.0) -> tuple[int, dict | str]:
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
    last = None
    while time.time() < deadline:
        try:
            code, body = http("GET", url, timeout=3.0)
            if code == 200:
                print(f"[seed] backend ready: {body}")
                return
            last = (code, body)
        except Exception as e:  # noqa: BLE001
            last = ("EXC", str(e))
        time.sleep(2.0)
    raise SystemExit(f"[seed] backend not ready after {timeout}s: {last}")


def login_otp(base: str, phone: str) -> dict:
    code, body = http(
        "POST", f"{base}/api/v1/auth/verify-otp",
        body={"phone": phone, "code": "000000"},
    )
    if code != 200:
        raise SystemExit(f"[seed] login failed for {phone}: {code} {body}")
    return body


def ensure_admin_user(compose_project: str = "yiluan-staging",
                      service: str = "backend-staging") -> None:
    """Create / update an admin user in the staging DB by running an
    ad-hoc python statement inside the backend container."""
    script = (
        "import asyncio, uuid\n"
        "from sqlalchemy import text\n"
        "from app.database import async_session\n"
        "ADMIN_PHONE='13900000000'\n"
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
        "-f", "docker-compose.staging.yml",
        "exec", "-T", service,
        "python", "-c", script,
    ]
    print(f"[seed] ensuring admin user via: {' '.join(cmd[:6])} ...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print("[seed] admin ensure stdout:", res.stdout)
        print("[seed] admin ensure stderr:", res.stderr)
        raise SystemExit("[seed] failed to create admin user")
    print(res.stdout.strip())


def seed_hospitals(base: str) -> None:
    code, body = http("POST", f"{base}/api/v1/hospitals/seed")
    if code != 200:
        print(f"[seed] hospital seed: code={code} body={body}")
        # Don't fatal — hospitals may already exist
    else:
        print(f"[seed] hospitals: {body}")


def seed_patients(base: str, n: int = 5) -> list[dict]:
    out = []
    for i in range(1, n + 1):
        phone = f"138000000{i:02d}"
        tok = login_otp(base, phone)
        out.append({"phone": phone, "user": tok["user"], "access_token": tok["access_token"]})
    print(f"[seed] patients: {[p['phone'] for p in out]}")
    return out


def seed_companions(base: str, admin_token: str, n: int = 3) -> list[dict]:
    out = []
    # Pick first available hospital ID for service_hospitals.
    code, hospitals = http("GET", f"{base}/api/v1/hospitals?page=1&page_size=1")
    hid = ""
    if code == 200 and isinstance(hospitals, dict):
        items = hospitals.get("items", []) or []
        if items:
            hid = items[0].get("id", "")

    for i in range(1, n + 1):
        phone = f"138000001{i:02d}"
        tok = login_otp(base, phone)
        access = tok["access_token"]
        uid = tok["user"]["id"]
        # apply as companion
        apply_code, apply_body = http(
            "POST", f"{base}/api/v1/companions/apply",
            headers={"authorization": f"Bearer {access}"},
            body={
                "real_name": f"Staging陪诊师{i}",
                "service_types": "full_accompany,half_accompany",
                "service_city": "北京",
                "service_area": "朝阳区,海淀区",
                "service_hospitals": hid,
                "bio": "staging seed companion",
            },
        )
        # apply may 400 if already applied — that's OK
        if apply_code not in (200, 201):
            print(f"[seed] companion apply {phone}: {apply_code} {str(apply_body)[:200]}")

        # approve via admin token
        # Need companion profile id, not user id. Look it up via admin
        # pending list (matches by user_id).
        list_code, list_body = http(
            "GET",
            f"{base}/api/v1/admin/companions/?page=1&page_size=100",
            headers={"X-Admin-Token": admin_token},
        )
        cid = None
        if list_code == 200 and isinstance(list_body, dict):
            for c in list_body.get("items", []) or []:
                if c.get("user_id") == uid or c.get("phone") == phone:
                    cid = c.get("id")
                    break
        if not cid:
            # Fall back: query directly via DB-style endpoint not available;
            # try /companions/me with the companion's own JWT.
            me_code, me_body = http(
                "GET", f"{base}/api/v1/companions/me",
                headers={"authorization": f"Bearer {access}"},
            )
            if me_code == 200 and isinstance(me_body, dict):
                cid = me_body.get("id")

        if cid:
            ap_code, ap_body = http(
                "POST",
                f"{base}/api/v1/admin/companions/{cid}/approve",
                headers={"X-Admin-Token": admin_token},
            )
            if ap_code not in (200, 201):
                print(f"[seed] companion approve {phone}: {ap_code} {ap_body}")

        # Re-login so role/roles claim is fresh
        tok = login_otp(base, phone)
        out.append({"phone": phone, "user": tok["user"], "access_token": tok["access_token"]})
    print(f"[seed] companions: {[c['phone'] for c in out]}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:18080")
    ap.add_argument("--admin-token", default="staging-admin-token")
    ap.add_argument("--compose-project", default="yiluan-staging")
    args = ap.parse_args()

    wait_backend(args.base)
    ensure_admin_user(compose_project=args.compose_project)
    seed_hospitals(args.base)
    seed_patients(args.base)
    seed_companions(args.base, admin_token=args.admin_token)

    print("[seed] OK — staging fixtures ready")
    return 0


if __name__ == "__main__":
    sys.exit(main())
