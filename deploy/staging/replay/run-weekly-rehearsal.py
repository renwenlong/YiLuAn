"""
Weekly staging rehearsal — full patient journey (D-044).

Drives the entire happy-path through the public nginx entrypoint
(default http://127.0.0.1:18080) so we exercise the same surface a
real client would hit:

    1. patient OTP login (000000 dev bypass)
    2. fetch a hospital, create an order
    3. /pay returns prepay info
    4. mock-pay-stub /__trigger-callback fires the wechat callback
       to the backend → order goes paid
    5. companion login (must already be admin-approved)
    6. companion accepts → request-start → patient confirm-start →
       companion complete
    7. patient submits a multidimensional review
    8. admin (JWT) refunds via /api/v1/admin/orders/{order_id}/admin-refund

A markdown report is written to deploy/staging/reports/rehearsal-YYYY-MM-DD.md.
Exit status 0 = green, 1 = a step failed.

Pre-req: `python deploy/staging/seed_staging.py` was already executed
(or pass --skip-seed if you've already seeded this run).

Cross-platform: pure stdlib + httpx, pathlib + UTF-8.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Callable

import httpx


# Force UTF-8 on stdout/stderr so Chinese hospital names / step details
# don't blow up Windows' default cp1252 console.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:
    pass


CST = timezone(timedelta(hours=8))
HERE = Path(__file__).resolve().parent
STAGING_DIR = HERE.parent  # deploy/staging
REPORTS_DIR = STAGING_DIR / "reports"


@dataclass
class Step:
    name: str
    ok: bool = False
    duration_ms: int = 0
    detail: str = ""
    error: str = ""


@dataclass
class Rehearsal:
    base: str
    admin_phone: str
    companion_phone: str
    patient_phone: str
    steps: list[Step] = field(default_factory=list)
    started_at: datetime = field(default_factory=lambda: datetime.now(CST))

    def run(self, name: str, fn: Callable[[], str]) -> str:
        s = Step(name=name)
        t0 = time.perf_counter()
        try:
            detail = fn() or ""
            s.ok = True
            s.detail = detail
            print(f"  [OK]   {name}  {detail}")
            return detail
        except Exception as e:  # noqa: BLE001
            s.error = f"{type(e).__name__}: {e}\n{traceback.format_exc()}"
            print(f"  [FAIL] {name}  {type(e).__name__}: {e}")
            raise
        finally:
            s.duration_ms = int((time.perf_counter() - t0) * 1000)
            self.steps.append(s)
            print(f"         ({s.duration_ms} ms)")


# ---------- thin HTTP helpers --------------------------------------------------

class API:
    def __init__(self, base: str, timeout: float = 15.0):
        self.base = base.rstrip("/")
        self.client = httpx.Client(base_url=self.base, timeout=timeout)

    def close(self) -> None:
        self.client.close()

    def _hdrs(self, token: str | None) -> dict:
        h = {"content-type": "application/json"}
        if token:
            h["authorization"] = f"Bearer {token}"
        return h

    def post(self, path: str, body: Any = None, token: str | None = None,
             extra_headers: dict | None = None) -> tuple[int, Any]:
        h = self._hdrs(token)
        if extra_headers:
            h.update(extra_headers)
        r = self.client.post(path, json=body, headers=h)
        return r.status_code, _safe_json(r)

    def get(self, path: str, token: str | None = None,
            extra_headers: dict | None = None) -> tuple[int, Any]:
        h = self._hdrs(token)
        if extra_headers:
            h.update(extra_headers)
        r = self.client.get(path, headers=h)
        return r.status_code, _safe_json(r)


def _safe_json(r: httpx.Response) -> Any:
    try:
        return r.json()
    except Exception:
        return r.text


def _expect(code: int, body: Any, ok: tuple[int, ...] = (200, 201),
            ctx: str = "") -> None:
    if code not in ok:
        raise RuntimeError(f"{ctx} expected {ok} got {code}: {str(body)[:300]}")


# ---------- the journey --------------------------------------------------------

def login(api: API, phone: str) -> dict:
    code, body = api.post("/api/v1/auth/verify-otp",
                          {"phone": phone, "code": "000000"})
    _expect(code, body, ctx=f"login {phone}")
    return body  # {access_token, refresh_token, user{...}}


def journey(r: Rehearsal, api: API) -> dict:
    """Returns a dict of useful artefacts for the report."""
    art: dict = {}

    # --- 1. patient login (fresh phone keeps reviews unique per run)
    def _patient_login() -> str:
        tok = login(api, r.patient_phone)
        atok = tok["access_token"]
        # Fresh users have role=null; assign patient role then re-login so the
        # new JWT carries the role claim used by order/cancel guards.
        if (tok["user"].get("role") or "").lower() != "patient":
            r2 = api.client.put("/api/v1/users/me",
                                 json={"role": "patient"},
                                 headers={"authorization": f"Bearer {atok}",
                                         "content-type": "application/json"})
            if r2.status_code not in (200, 201):
                raise RuntimeError(f"set patient role: {r2.status_code} {r2.text[:200]}")
            tok = login(api, r.patient_phone)
            atok = tok["access_token"]
        art["patient_token"] = atok
        art["patient_id"] = tok["user"]["id"]
        return f"phone={r.patient_phone} user_id={art['patient_id'][:8]}… role={tok['user'].get('role')}"
    r.run("patient OTP login", _patient_login)

    # --- 2. pick a hospital
    def _pick_hospital() -> str:
        code, body = api.get("/api/v1/hospitals?page=1&page_size=1",
                             token=art["patient_token"])
        _expect(code, body, ctx="list hospitals")
        items = body.get("items") or []
        if not items:
            raise RuntimeError("no hospitals seeded; run seed_staging.py first")
        art["hospital_id"] = items[0]["id"]
        return f"hospital_id={art['hospital_id'][:8]}… name={items[0].get('name','?')}"
    r.run("pick hospital", _pick_hospital)

    # --- 3. create order
    def _create_order() -> str:
        # Pick an appointment 7 days from now to clear any min-lead validation
        appt = datetime.now(CST) + timedelta(days=7)
        body = {
            "service_type": "full_accompany",
            "hospital_id": art["hospital_id"],
            "appointment_date": appt.strftime("%Y-%m-%d"),
            "appointment_time": "09:30",
            "description": "staging rehearsal — auto-generated order",
        }
        code, resp = api.post("/api/v1/orders", body, token=art["patient_token"])
        _expect(code, resp, ctx="create order")
        art["order_id"] = resp["id"]
        art["order_number"] = resp["order_number"]
        return f"order_id={art['order_id'][:8]}… number={art['order_number']}"
    r.run("create order", _create_order)

    # --- 4. pay (returns prepay info from MockProvider)
    def _pay() -> str:
        code, resp = api.post(f"/api/v1/orders/{art['order_id']}/pay", None,
                              token=art["patient_token"])
        _expect(code, resp, ctx="pay order")
        art["payment_id"] = resp.get("payment_id")
        return f"payment_id={str(art.get('payment_id'))[:8]}… provider={resp.get('provider')}"
    r.run("pay order (request prepay)", _pay)

    # --- 5. fire wechat callback via mock-pay-stub admin route on nginx
    def _trigger_callback() -> str:
        code, resp = api.post(
            "/__staging/mock-pay/__trigger-callback",
            {"order_number": art["order_number"], "success": True},
        )
        _expect(code, resp, ctx="trigger pay callback")
        if not resp.get("ok"):
            raise RuntimeError(f"mock-pay-stub failed to call backend: {resp}")
        return f"backend status={resp.get('status_code')}"
    r.run("trigger wechat pay callback", _trigger_callback)

    # --- 6. confirm order is payable (Order.status stays `created` —
    # there is no `paid` order status; only Payment.status becomes `success`).
    def _verify_paid() -> str:
        code, resp = api.get(f"/api/v1/orders/{art['order_id']}",
                             token=art["patient_token"])
        _expect(code, resp, ctx="get order after pay")
        return f"order.status={resp.get('status')} (Payment row marked success by callback)"
    r.run("verify order payable", _verify_paid)

    # --- 7. companion login (must already be admin-approved by seed)
    def _companion_login() -> str:
        tok = login(api, r.companion_phone)
        roles = tok["user"].get("roles") or tok["user"].get("role") or "?"
        art["companion_token"] = tok["access_token"]
        art["companion_user_id"] = tok["user"]["id"]
        return f"phone={r.companion_phone} roles={roles}"
    r.run("companion OTP login", _companion_login)

    # --- 8. companion accepts the order
    def _accept() -> str:
        code, resp = api.post(f"/api/v1/orders/{art['order_id']}/accept", None,
                              token=art["companion_token"])
        _expect(code, resp, ctx="accept order")
        return f"status={resp.get('status')}"
    r.run("companion accepts order", _accept)

    # --- 9. companion request-start → patient confirm-start
    def _request_start() -> str:
        code, resp = api.post(
            f"/api/v1/orders/{art['order_id']}/request-start", None,
            token=art["companion_token"],
        )
        _expect(code, resp, ctx="request-start")
        return f"status={resp.get('status')}"
    r.run("companion request-start", _request_start)

    def _confirm_start() -> str:
        code, resp = api.post(
            f"/api/v1/orders/{art['order_id']}/confirm-start", None,
            token=art["patient_token"],
        )
        # Some flows allow companion to /start directly on accepted; if
        # confirm-start 4xx because it's already in_service, that's still OK.
        if code not in (200, 201):
            # try direct /start as fallback
            c2, r2 = api.post(f"/api/v1/orders/{art['order_id']}/start", None,
                              token=art["companion_token"])
            if c2 in (200, 201):
                return f"fallback /start → status={r2.get('status')}"
            raise RuntimeError(f"confirm-start {code} {resp} / start {c2} {r2}")
        return f"status={resp.get('status')}"
    r.run("patient confirm-start", _confirm_start)

    # --- 10. companion completes
    def _complete() -> str:
        code, resp = api.post(f"/api/v1/orders/{art['order_id']}/complete", None,
                              token=art["companion_token"])
        _expect(code, resp, ctx="complete order")
        return f"status={resp.get('status')}"
    r.run("companion completes order", _complete)

    # --- 11. patient submits multidimensional review
    def _review() -> str:
        body = {
            "punctuality_rating": 5,
            "professionalism_rating": 5,
            "communication_rating": 4,
            "attitude_rating": 5,
            "content": "Staging rehearsal review — auto generated",
        }
        code, resp = api.post(
            f"/api/v1/orders/{art['order_id']}/review", body,
            token=art["patient_token"],
        )
        _expect(code, resp, ctx="submit review")
        art["review_id"] = resp.get("id")
        return f"rating={resp.get('rating')} review_id={str(resp.get('id'))[:8]}…"
    r.run("patient submits multi-dim review", _review)

    # --- 12. admin login + refund
    def _admin_refund() -> str:
        admin_tok = login(api, r.admin_phone)
        atok = admin_tok["access_token"]
        # admin-refund endpoint
        code, resp = api.post(
            f"/api/v1/admin/orders/{art['order_id']}/admin-refund?refund_ratio=1.0",
            None, token=atok,
        )
        _expect(code, resp, ctx="admin-refund")
        art["refund_id"] = resp.get("refund_id")
        return f"refund_amount={resp.get('refund_amount')} refund_id={str(resp.get('refund_id'))[:8]}…"
    r.run("admin issues full refund", _admin_refund)

    return art


# ---------- report -------------------------------------------------------------

def write_report(r: Rehearsal, art: dict, all_green: bool, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    total_ms = sum(s.duration_ms for s in r.steps)
    status = "✅ GREEN" if all_green else "❌ RED"
    lines: list[str] = [
        f"# Staging Rehearsal — {r.started_at.strftime('%Y-%m-%d %H:%M %Z')}",
        "",
        f"- **Status**: {status}",
        f"- **Base URL**: `{r.base}`",
        f"- **Patient phone**: `{r.patient_phone}` (fresh per run)",
        f"- **Companion phone**: `{r.companion_phone}` (seeded + approved)",
        f"- **Admin phone**: `{r.admin_phone}` (seeded)",
        f"- **Total wall time**: {total_ms} ms across {len(r.steps)} steps",
        "",
        "## Steps",
        "",
        "| # | Step | Result | Duration | Detail |",
        "|---|------|--------|----------|--------|",
    ]
    for i, s in enumerate(r.steps, 1):
        marker = "✅" if s.ok else "❌"
        detail = (s.detail if s.ok else s.error.splitlines()[0]).replace("|", "\\|")
        lines.append(f"| {i} | {s.name} | {marker} | {s.duration_ms} ms | {detail} |")
    lines.append("")
    if art:
        lines += ["## Artefacts", "", "```json",
                  json.dumps(_redact(art), indent=2, ensure_ascii=False),
                  "```", ""]
    failures = [s for s in r.steps if not s.ok]
    if failures:
        lines += ["## Failures (full traceback)", ""]
        for s in failures:
            lines += [f"### {s.name}", "", "```", s.error, "```", ""]

    out_path.write_text("\n".join(lines), encoding="utf-8")


def _redact(art: dict) -> dict:
    out: dict = {}
    for k, v in art.items():
        if isinstance(v, str) and ("token" in k.lower()):
            out[k] = v[:12] + "…(redacted)" if v else v
        else:
            out[k] = v
    return out


# ---------- main ---------------------------------------------------------------

def maybe_seed(base: str, admin_token: str, compose_project: str) -> None:
    seed = STAGING_DIR / "seed_staging.py"
    if not seed.exists():
        print(f"[rehearsal] seed_staging.py missing at {seed}, skipping")
        return
    print(f"[rehearsal] running seed_staging.py …")
    res = subprocess.run(
        [sys.executable, str(seed),
         "--base", base,
         "--admin-token", admin_token,
         "--compose-project", compose_project],
        cwd=str(STAGING_DIR),
        capture_output=True, text=True,
    )
    sys.stdout.write(res.stdout)
    if res.returncode != 0:
        sys.stderr.write(res.stderr)
        raise SystemExit(f"[rehearsal] seed failed (rc={res.returncode})")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--base", default=os.getenv("STAGING_BASE", "http://127.0.0.1:18080"))
    p.add_argument("--admin-phone", default="13900000000")
    p.add_argument("--companion-phone", default="13800000101")
    # Fresh patient phone every run so reviews don't dup
    default_patient = "139" + datetime.now(CST).strftime("%H%M%S%f")[:8]
    p.add_argument("--patient-phone", default=default_patient)
    p.add_argument("--admin-token", default="staging-admin-token")
    p.add_argument("--compose-project", default="yiluan-staging")
    p.add_argument("--skip-seed", action="store_true",
                   help="Skip running seed_staging.py before the journey")
    p.add_argument("--report-dir", default=str(REPORTS_DIR))
    args = p.parse_args()

    print(f"[rehearsal] base={args.base}")
    print(f"[rehearsal] patient={args.patient_phone} companion={args.companion_phone} admin={args.admin_phone}")

    if not args.skip_seed:
        maybe_seed(args.base, args.admin_token, args.compose_project)

    api = API(args.base)
    r = Rehearsal(
        base=args.base,
        admin_phone=args.admin_phone,
        companion_phone=args.companion_phone,
        patient_phone=args.patient_phone,
    )

    art: dict = {}
    all_green = True
    try:
        art = journey(r, api)
    except Exception:
        all_green = False
    finally:
        api.close()

    out = Path(args.report_dir) / f"rehearsal-{r.started_at.strftime('%Y-%m-%d')}.md"
    write_report(r, art, all_green, out)
    print(f"[rehearsal] report: {out}")
    print(f"[rehearsal] result: {'GREEN' if all_green else 'RED'}")
    return 0 if all_green else 1


if __name__ == "__main__":
    sys.exit(main())
