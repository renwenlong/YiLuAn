# Staging Rehearsal — 2026-05-19 22:18 UTC+08:00

- **Status**: ✅ GREEN
- **Base URL**: `http://127.0.0.1:18080`
- **Patient phone**: `13922184615` (fresh per run)
- **Companion phone**: `13800000101` (seeded + approved)
- **Admin phone**: `13900000000` (seeded)
- **Total wall time**: 528 ms across 13 steps

## Steps

| # | Step | Result | Duration | Detail |
|---|------|--------|----------|--------|
| 1 | patient OTP login | ✅ | 34 ms | phone=13922184615 user_id=d33694a0… role=patient |
| 2 | pick hospital | ✅ | 3 ms | hospital_id=b072c910… name=上海中医药大学附属龙华医院 |
| 3 | create order | ✅ | 15 ms | order_id=9fdddf66… number=YLA920032626042F3E9 |
| 4 | pay order (request prepay) | ✅ | 25 ms | payment_id=09182fc5… provider=mock |
| 5 | trigger wechat pay callback | ✅ | 30 ms | backend status=200 |
| 6 | verify order payable | ✅ | 8 ms | order.status=created (Payment row marked success by callback) |
| 7 | companion OTP login | ✅ | 5 ms | phone=13800000101 roles=['companion'] |
| 8 | companion accepts order | ✅ | 15 ms | status=accepted |
| 9 | companion request-start | ✅ | 10 ms | status=accepted |
| 10 | patient confirm-start | ✅ | 16 ms | status=in_progress |
| 11 | companion completes order | ✅ | 14 ms | status=completed |
| 12 | patient submits multi-dim review | ✅ | 18 ms | rating=5 review_id=b630e224… |
| 13 | admin issues full refund | ✅ | 335 ms | refund_amount=299.00 refund_id=RCBD8C1F… |

## Artefacts

```json
{
  "patient_token": "eyJhbGciOiJI…(redacted)",
  "patient_id": "d33694a0-0a4c-43ea-bbde-8780f1a8cec9",
  "hospital_id": "b072c910-7231-417a-aedb-70ee0a9407a3",
  "order_id": "9fdddf66-ef34-4978-9bd5-4c79eb952e2c",
  "order_number": "YLA920032626042F3E9",
  "order_price": "299.0",
  "payment_id": "09182fc5-4139-4305-a16c-43615d321848",
  "companion_token": "eyJhbGciOiJI…(redacted)",
  "companion_user_id": "b8c68ac8-161a-4068-a1fb-427b16a366b8",
  "review_id": "b630e224-92e2-4875-b161-f7bcf4e88cb2",
  "refund_id": "RCBD8C1FA2AD64AD0"
}
```
