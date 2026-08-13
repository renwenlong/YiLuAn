# Staging 手动 Redeploy 快速手册（ADR-0059 方案 C）

> **用途**：把 `origin/main` 上已通过 required CI 的明确 commit 部署到 staging。
> **当前边界**：受限 SSH / deploy wrapper 尚未由帝君配置前，本手册由帝君在
> staging 主机执行；胡桃只提供 SHA 与 CI 证据。不得把 private key 放进 agent
> workspace，也不得给 agent 任意远程 shell。

## 1. 部署前确认

记录目标 commit，且只允许部署 `origin/main` 上的 SHA：

```bash
cd <staging-checkout>
git fetch origin main
TARGET_SHA="$(git rev-parse origin/main)"
git merge-base --is-ancestor "$TARGET_SHA" origin/main
printf 'target=%s\n' "$TARGET_SHA"
```

如果需要部署的 SHA 不是当前 `origin/main`，停止并先确认原因；不得用本地 feature
branch、未 push commit 或任意 tag 替代。

## 2. Required CI gate（不可跳过）

```bash
cd <staging-checkout>
deploy/staging/check-main-ci.sh --sha "$TARGET_SHA"
```

只有脚本输出 `CI gate PASSED` 且退出码为 0 才能继续。以下任一情况立即停止：

- required check 缺失；
- check pending / failure / cancelled / skipped / neutral；
- `gh`、`python3` 或 GitHub API 不可用；
- 目标 SHA 与 `origin/main` 不一致。

## 3. 更新 checkout 并部署

```bash
cd <staging-checkout>
git checkout --detach "$TARGET_SHA"
cd deploy
./up.sh staging
```

`up.sh` 会构建并拉起 compose 栈、执行 migration、等待 backend health 并 seed
staging fixtures。不要使用 `git reset --hard` 清理未知改动；checkout 不干净时停止，
先确认文件归属。

## 4. 验活

```bash
curl -fsS http://127.0.0.1:18080/api/v1/ping
curl -fsS http://127.0.0.1:18080/health
curl -fsS http://127.0.0.1:18080/readiness
curl -fsS http://127.0.0.1:18080/__staging/mock-pay/health
curl -fsS http://127.0.0.1:18080/__staging/mock-sms/health
```

需要完整业务演练时：

```bash
cd <staging-checkout>
python3 deploy/staging/replay/run-weekly-rehearsal.py --skip-seed
```

故障定位与 teardown 见 `docs/STAGING_REHEARSAL_RUNBOOK.md`。

## 5. 回报与审计

每次 redeploy 在群里记录：

```text
staging redeploy
- SHA: <TARGET_SHA>
- URL: <staging URL>
- deployed_at: <UTC ISO-8601>
- operator: <operator / restricted wrapper identity>
- CI gate: 5/5 success
- health: ping/health/readiness/mock-pay/mock-sms PASS
- rehearsal: PASS / NOT_RUN / FAIL(<report>)
```

没有完整记录时，不得对外声称 staging 已更新。

## 6. 受限 wrapper 的主机侧契约

帝君配置的受限入口应只接受一个参数：`<origin-main-sha>`，并按固定顺序执行：

1. fetch `origin/main` 并验证参数 SHA 属于 `origin/main`；
2. 运行 `check-main-ci.sh --sha <sha>`；
3. checkout 该 SHA；
4. 运行 `deploy/up.sh staging`；
5. 执行 §4 验活；
6. 写入 §5 审计记录。

wrapper 必须拒绝额外 shell 参数、环境覆盖和任意命令拼接。推荐 bastion 白名单脚本
或短时证书调用；禁止常驻 full SSH key。

仓库提供 `deploy/staging/redeploy-wrapper.sh` 作为 I-3 host-side 实现。安装时必须：

- 复制到 repository 外的 root-owned `/opt/yiluan/redeploy.sh`，禁止 deploy
  identity 修改；受限入口只允许触发该绝对路径；保留脚本的
  `#!/usr/bin/env -S -i /bin/bash --noprofile --norc` launcher，使调用方环境在 Bash
  启动前清空，禁止 `BASH_ENV` 或继承 shell options 注入 startup code；主机必须使用
  支持 `env -S` 的 GNU coreutils，安装验收须包含恶意 `BASH_ENV` 与 hostile `PATH`
  解释器选择负测；
- 同样将 `check-main-ci.sh` 与 `_parse_required_checks.py` 复制到 wrapper 声明的
  `/usr/local/libexec/yiluan-staging-deploy/`；
- 预创建 root-owned audit log，并在支持该属性的文件系统上执行
  `chattr +a /var/log/yiluan-staging-redeploy.log`；wrapper 每次调用都会用
  `lsattr -d` 验证 append-only 位，缺失或无法验证时 fail closed。普通的可写文件权限
  **不等于** append-only；
- 单独预创建 deploy identity 可写的 lock file；
- SSH/bastion 入口只映射到该 wrapper，不提供交互 shell；
- deploy identity 只获得 Docker socket、目标 checkout 和上述日志所需的最小权限。

仓库内副本用于 review 与安装源，不能直接作为长期受限入口，避免目标 checkout
修改下一次调用的权限边界。

管理员安装 audit sink 时必须保留已有历史，不得用重定向或 `install /dev/null`
覆盖已存在的日志。以下是契约示例（实际执行仍需单独授权）：

```bash
if [ ! -e /var/log/yiluan-staging-redeploy.log ]; then
  install -o root -g yiluan-deploy -m 0620 /dev/null \
    /var/log/yiluan-staging-redeploy.log
fi
test -f /var/log/yiluan-staging-redeploy.log
test ! -L /var/log/yiluan-staging-redeploy.log
chown root:yiluan-deploy /var/log/yiluan-staging-redeploy.log
chmod 0620 /var/log/yiluan-staging-redeploy.log
chattr +a /var/log/yiluan-staging-redeploy.log
lsattr -d /var/log/yiluan-staging-redeploy.log
```

首次启用前必须由管理员做正、负向验收：`lsattr` 的属性字段包含 `a`；deploy
identity 的 `>>` 追加成功；同一 identity 无法清除 append-only 属性、替换 inode、
删除、截断或原位改写日志，且原有首行仍在。可用以下固定测试（测试追加行本身保留为
审计证据）：

```bash
runuser -u yiluan-deploy -- sh -c \
  'printf "%s\n" "append-only acceptance" >> /var/log/yiluan-staging-redeploy.log'
first_line="$(head -n 1 /var/log/yiluan-staging-redeploy.log)"
if runuser -u yiluan-deploy -- chattr -a \
  /var/log/yiluan-staging-redeploy.log; then
  echo "FAIL: deploy identity can clear append-only protection" >&2
  exit 1
fi
if runuser -u yiluan-deploy -- sh -c \
  'replacement="$(mktemp)"; printf "%s\n" forged > "$replacement"; \
   if mv -f "$replacement" /var/log/yiluan-staging-redeploy.log; then \
     exit 0; else rm -f "$replacement"; exit 1; fi'; then
  echo "FAIL: deploy identity can replace the audit inode" >&2
  exit 1
fi
if runuser -u yiluan-deploy -- rm -f \
  /var/log/yiluan-staging-redeploy.log; then
  echo "FAIL: deploy identity can delete the audit log" >&2
  exit 1
fi
if runuser -u yiluan-deploy -- sh -c \
  ': > /var/log/yiluan-staging-redeploy.log'; then
  echo "FAIL: audit log can be truncated" >&2
  exit 1
fi
if runuser -u yiluan-deploy -- sed -i '1s/.*/tampered/' \
  /var/log/yiluan-staging-redeploy.log; then
  echo "FAIL: audit history can be rewritten" >&2
  exit 1
fi
test "$(head -n 1 /var/log/yiluan-staging-redeploy.log)" = "$first_line"
```

若目标文件系统不支持 append-only 属性，安装必须停止；不得降级为普通可写文件。
需另行评审 journald/远端 WORM 等等价机制并同步修改 wrapper 后，方可启用。
