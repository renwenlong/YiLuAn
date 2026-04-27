#!/usr/bin/env bash
# YiLuAn Staging - up.sh (D-044)
set -euo pipefail
cd "$(dirname "$0")"

echo "==> docker compose up -d (build mocks if needed)"
docker compose -p yiluan-staging -f docker-compose.staging.yml up -d --build

echo "==> waiting for backend healthcheck..."
deadline=$(( $(date +%s) + 180 ))
while [ "$(date +%s)" -lt "$deadline" ]; do
  if curl -fsS --max-time 3 http://127.0.0.1:18080/api/v1/ping >/dev/null 2>&1; then
    echo "backend ready"
    break
  fi
  sleep 3
done

echo "==> running alembic upgrade head"
docker compose -p yiluan-staging -f docker-compose.staging.yml exec -T backend-staging alembic upgrade head

echo "==> seeding staging fixtures"
python3 seed_staging.py --base http://127.0.0.1:18080 --admin-token staging-admin-token --compose-project yiluan-staging

echo "==> staging is up"
echo "   API gateway : http://127.0.0.1:18080/api/v1/ping"
echo "   Health      : http://127.0.0.1:18080/health"
echo "   Readiness   : http://127.0.0.1:18080/readiness"
echo "   Mock pay    : http://127.0.0.1:18080/__staging/mock-pay/health"
echo "   Mock sms    : http://127.0.0.1:18080/__staging/mock-sms/health"
echo ""
echo "Run rehearsal: python3 replay/run-weekly-rehearsal.py"
echo "Tear down   : ./down.sh"
