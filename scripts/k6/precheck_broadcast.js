/**
 * k6 perf SLO script for S3-DEV-003-PRECHECK-BACKEND broadcast latency.
 *
 * Goal: assert WS push latency p95 ≤ 5s under load (design §9 SLO).
 *
 * Topology
 * --------
 * 1. N=50 virtual users open WS to /api/v1/ws/v1/orders/{order_id}/precheck
 *    each subscribed to a distinct order_id.
 * 2. A separate trigger loop (3/s for 60s) hits POST /api/v1/admin/cache/invalidate
 *    against each subscribed order, causing the aggregator to
 *    recompute + push precheck.status.updated to that order's WS room.
 * 3. The WS handler records the receive timestamp; latency = receive ts -
 *    publish ts (envelope `ts` field is broker publish time).
 *
 * SLOs (assert thresholds)
 * ------------------------
 * - precheck_ws_recv_latency_seconds p95 ≤ 5s
 * - precheck_invalidate_endpoint_duration p95 ≤ 1s
 * - WS connection error rate < 1%
 *
 * Usage
 * -----
 * Staging (default):
 *   k6 run scripts/k6/precheck_broadcast.js
 *
 * Custom base URL / token:
 *   BASE_URL=https://staging.example.com \
 *   PATIENT_TOKEN=<jwt> \
 *   ADMIN_TOKEN=<jwt> \
 *   k6 run scripts/k6/precheck_broadcast.js
 *
 * Notes
 * -----
 * - Not part of CI; run on staging on-demand before c5 → main merge.
 * - Mirrors the chat WS broker perf script (scripts/k6/chat_broker.js
 *   pattern if/when added). Same instrumentation philosophy: real
 *   broker, real handler, mock backend not used.
 * - ORDER_IDS must exist in the staging DB and be owned by PATIENT_TOKEN;
 *   seed via admin tooling or copy from staging seed fixtures.
 */

import http from 'k6/http';
import ws from 'k6/ws';
import { check, sleep } from 'k6';
import { Trend, Rate, Counter } from 'k6/metrics';

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const PATIENT_TOKEN = __ENV.PATIENT_TOKEN || '';
const ADMIN_TOKEN = __ENV.ADMIN_TOKEN || '';
const ORDER_IDS = (__ENV.ORDER_IDS || '').split(',').filter(Boolean);

if (!PATIENT_TOKEN || !ADMIN_TOKEN || ORDER_IDS.length === 0) {
  throw new Error(
    'PATIENT_TOKEN + ADMIN_TOKEN + ORDER_IDS (comma-separated) required'
  );
}

// Custom metrics
const wsLatency = new Trend('precheck_ws_recv_latency_seconds', true);
const invalidateLatency = new Trend(
  'precheck_invalidate_endpoint_duration', true
);
const wsErrors = new Rate('precheck_ws_error_rate');
const messagesReceived = new Counter('precheck_ws_messages_received');

export const options = {
  scenarios: {
    ws_subscribers: {
      executor: 'constant-vus',
      exec: 'wsSubscriber',
      vus: ORDER_IDS.length,
      duration: '90s',
    },
    invalidate_trigger: {
      executor: 'constant-arrival-rate',
      exec: 'invalidateTrigger',
      rate: 3,                  // 3/s
      timeUnit: '1s',
      duration: '60s',
      preAllocatedVUs: 5,
      maxVUs: 10,
      startTime: '15s',         // let WS subscribers connect first
    },
  },
  thresholds: {
    'precheck_ws_recv_latency_seconds': ['p(95)<5'],
    'precheck_invalidate_endpoint_duration': ['p(95)<1000'],
    'precheck_ws_error_rate': ['rate<0.01'],
  },
};

export function wsSubscriber() {
  const orderId = ORDER_IDS[__VU - 1] || ORDER_IDS[0];
  const wsBase = BASE_URL.replace(/^http/, 'ws');
  const url = `${wsBase}/api/v1/ws/v1/orders/${orderId}/precheck?token=${PATIENT_TOKEN}`;

  const res = ws.connect(url, {}, (socket) => {
    socket.on('open', () => {
      // Keep the connection alive with a ping every 25s (idle timeout 90s).
      socket.setInterval(() => socket.ping(), 25 * 1000);
    });

    socket.on('message', (rawMsg) => {
      try {
        const data = JSON.parse(rawMsg);
        if (data.event === 'precheck.status.updated' && data.ts) {
          const publishMs = Date.parse(data.ts);
          const recvMs = Date.now();
          const latencyS = (recvMs - publishMs) / 1000;
          if (latencyS >= 0 && latencyS < 60) {
            wsLatency.add(latencyS);
            messagesReceived.add(1);
          }
        }
      } catch (e) {
        wsErrors.add(true);
      }
    });

    socket.on('error', () => wsErrors.add(true));
    socket.on('close', () => {});

    // Hold the connection for the scenario duration.
    socket.setTimeout(() => socket.close(), 85 * 1000);
  });

  check(res, { 'ws upgrade 101': (r) => r && r.status === 101 });
}

export function invalidateTrigger() {
  // Pick a random subscribed order to trigger.
  const orderId = ORDER_IDS[Math.floor(Math.random() * ORDER_IDS.length)];

  const payload = JSON.stringify({ order_id: orderId });
  const params = {
    headers: {
      Authorization: `Bearer ${ADMIN_TOKEN}`,
      'Content-Type': 'application/json',
    },
  };

  const start = Date.now();
  const res = http.post(
    `${BASE_URL}/api/v1/admin/cache/invalidate`,
    payload,
    params
  );
  invalidateLatency.add(Date.now() - start);

  check(res, {
    'invalidate 200': (r) => r.status === 200,
    'broadcast field present': (r) =>
      r.body && r.body.indexOf('broadcast') !== -1,
  });
}

export function setup() {
  console.log(`Setup: BASE_URL=${BASE_URL}, ${ORDER_IDS.length} order_ids`);
}

export function teardown() {
  console.log('Done');
}
