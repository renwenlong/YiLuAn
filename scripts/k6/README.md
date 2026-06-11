# k6 performance scripts

Staging on-demand load tests. **Not** part of CI — run manually before
significant infra / broker / WS handler changes hit production.

## Prerequisites

- [k6](https://k6.io/docs/get-started/installation/) ≥ v0.50 installed locally
- Staging credentials + a set of test order_ids owned by a single patient

## Scripts

### `precheck_broadcast.js`

Validates `S3-DEV-003-PRECHECK-BACKEND` broadcast latency SLO:

- **WS push p95 ≤ 5s** (end-to-end: admin invalidate → aggregator
  recompute → broker fanout → client receive)
- **Admin invalidate endpoint p95 ≤ 1s**
- **WS error rate < 1%**

Usage:

```bash
# Default (localhost backend)
k6 run scripts/k6/precheck_broadcast.js

# Staging
BASE_URL=https://staging.example.com \
  PATIENT_TOKEN=<jwt-for-patient-owning-orders> \
  ADMIN_TOKEN=<jwt-for-super-admin> \
  ORDER_IDS=<uuid1>,<uuid2>,<uuid3>,... \
  k6 run scripts/k6/precheck_broadcast.js
```

50 VUs subscribe via WS (one per order), then a 3-RPS invalidate
trigger loop fires for 60s. Each VU records the latency from the
broker publish timestamp (envelope `ts` field) to the client-side
receive timestamp.

### Topology

```
┌───────────────┐    POST /admin/cache/invalidate         ┌──────────────┐
│ k6 trigger VU ├─────────────────────────────────────────►│  backend     │
└───────────────┘                                          │              │
                                                           │ aggregator   │
                                                           │   .evaluate  │
                                                           │ +broadcast   │
                                                           │   _facade    │
                                                           └──────┬───────┘
                                                                  │ push_to_key
                                                                  ▼
                                                           ┌──────────────┐
┌──────────────────┐  WS recv                              │ WS broker    │
│ k6 subscriber VU │◄──────────────────────────────────────┤ (in-process  │
└──────────────────┘                                       │  or Redis)   │
                                                           └──────────────┘
```

### Output

k6 prints a summary including:

- `precheck_ws_recv_latency_seconds` (Trend, threshold p95 < 5)
- `precheck_invalidate_endpoint_duration` (Trend, threshold p95 < 1000)
- `precheck_ws_error_rate` (Rate, threshold < 0.01)
- `precheck_ws_messages_received` (Counter)

A non-zero exit code means a threshold failed — fix or document the
regression before merging.

## Pattern

Mirrors the chat WS broker perf approach (see `chat_broker.js` if/when
added): real broker, real backend, no business-data mock. Aim for the
script to be runnable against staging without code changes — pass
config via environment variables only.
