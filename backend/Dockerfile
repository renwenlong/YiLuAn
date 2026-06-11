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

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
