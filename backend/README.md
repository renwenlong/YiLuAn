# YiLuAn Backend

## Run with Docker

默认后端环境是 **staging**。从仓库根目录旁的 `deploy/` 启动：

```bash
cd ../deploy
./up.sh            # 等同 ./up.sh staging，自动叠加 env.staging.local（若存在）
```

本地微信/联调也走 staging nginx：`http://127.0.0.1:18080/api/v1`。

## Run tests

```bash
cd backend
python -m pytest
```
