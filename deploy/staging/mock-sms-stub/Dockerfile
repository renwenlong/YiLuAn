FROM python:3.11-slim

WORKDIR /app

RUN pip install --no-cache-dir fastapi==0.115.0 uvicorn[standard]==0.32.0 pydantic==2.9.2

COPY app.py .

EXPOSE 8002

HEALTHCHECK --interval=10s --timeout=3s --retries=5 \
  CMD python -c "import urllib.request,sys; \
  sys.exit(0) if urllib.request.urlopen('http://127.0.0.1:8002/health',timeout=2).status==200 else sys.exit(1)" || exit 1

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8002"]
