FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi==0.115.*" \
    "uvicorn[standard]==0.30.*" \
    "httpx==0.27.*"

COPY wechat-work-webhook.py /app/wechat-work-webhook.py

EXPOSE 5001

# Use module-loading via uvicorn factory pattern; the file has a hyphen so
# we import it via a small shim.
RUN printf "import importlib.util, sys\nspec = importlib.util.spec_from_file_location('wechat_work_webhook', '/app/wechat-work-webhook.py')\nmod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)\nsys.modules['wechat_work_webhook'] = mod\napp = mod.app\n" > /app/asgi.py

CMD ["uvicorn", "asgi:app", "--host", "0.0.0.0", "--port", "5001"]
