FROM python:3.11-slim

WORKDIR /app

# build context 在 repo 根 (deploy/docker-compose.yml: context: ..),
# 所有 COPY 源路径都相对 repo 根, 目标路径相对 /app (WORKDIR) 或 / (绝对).

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/alembic/ alembic/
COPY backend/alembic.ini .
COPY backend/app/ app/

# S3-BUG-003: COPY medical-content yml 进 /docs/medical-content/.
# _DEFAULT_YML_PATH = Path(__file__).resolve().parents[3] / "docs" / "medical-content"
# 容器内: __file__ = /app/app/services/ai_prep_filter.py, parents[3] = /,
# 故 yml 必须放 /docs/medical-content/. SoT 在 repo 根 docs/medical-content/, 与
# admin PR review workflow 一致 — 不引入副本.
COPY docs/medical-content/ /docs/medical-content/

# S2-OPS-A-CANARY-WHITELIST-LAUNCH AC-2 (PR #302 follow-up fix): COPY canary
# whitelist yml 进 /deploy/canary/. 同 S3-BUG-003 bug 模式 (反案 #11) —
# canary_whitelist._DEFAULT_YML_PATH = Path(__file__).resolve().parents[3] /
# "deploy" / "canary" / "whitelist_phones.yaml". 容器内 __file__ =
# /app/app/services/canary_whitelist.py, parents[3] = /, 故 yml 必须在
# /deploy/canary/. 不 COPY → fail-closed → 全员 403 → 灰度业务失效.
COPY deploy/canary/ /deploy/canary/

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
