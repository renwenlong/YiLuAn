# Staging Rehearsal — 2026-04-27 13:14 UTC+08:00

- **Status**: ✅ GREEN
- **Base URL**: `http://127.0.0.1:18080`
- **Patient phone**: `13913142445` (fresh per run)
- **Companion phone**: `13800000101` (seeded + approved)
- **Admin phone**: `13900000000` (seeded)
- **Total wall time**: 243 ms across 13 steps

## Steps

| # | Step | Result | Duration | Detail |
|---|------|--------|----------|--------|
| 1 | patient OTP login | ✅ | 41 ms | phone=13913142445 user_id=d2a2d1a1… role=patient |
| 2 | pick hospital | ✅ | 4 ms | hospital_id=5aff5e10… name=上海中医药大学附属龙华医院 |
| 3 | create order | ✅ | 16 ms | order_id=34bff838… number=YLA7266865064346797 |
| 4 | pay order (request prepay) | ✅ | 24 ms | payment_id=06684e81… provider=mock |
| 5 | trigger wechat pay callback | ✅ | 26 ms | backend status=200 |
| 6 | verify order payable | ✅ | 9 ms | order.status=created (Payment row marked success by callback) |
| 7 | companion OTP login | ✅ | 6 ms | phone=13800000101 roles=['companion'] |
| 8 | companion accepts order | ✅ | 19 ms | status=accepted |
| 9 | companion request-start | ✅ | 13 ms | status=accepted |
| 10 | patient confirm-start | ✅ | 19 ms | status=in_progress |
| 11 | companion completes order | ✅ | 15 ms | status=completed |
| 12 | patient submits multi-dim review | ✅ | 32 ms | rating=5 review_id=f2e523dc… |
| 13 | admin issues full refund | ✅ | 19 ms | refund_amount=299.0 refund_id=e87450bb… |

## Artefacts

```json
{
  "patient_token": "eyJhbGciOiJI…(redacted)",
  "patient_id": "d2a2d1a1-5c5a-4ead-8a87-7dfdbda7aa40",
  "hospital_id": "5aff5e10-8e6a-4995-846c-785367fbe650",
  "order_id": "34bff838-ec04-4182-b552-4f47168d0b5f",
  "order_number": "YLA7266865064346797",
  "payment_id": "06684e81-a342-43cd-addf-422ec7fd2557",
  "companion_token": "eyJhbGciOiJI…(redacted)",
  "companion_user_id": "53ce0b4d-1708-4ddf-9361-d1bd77c95582",
  "review_id": "f2e523dc-4169-4727-b517-e172687af563",
  "refund_id": "e87450bb-2bcb-4f5a-aa21-fefa10a36a58"
}
```
