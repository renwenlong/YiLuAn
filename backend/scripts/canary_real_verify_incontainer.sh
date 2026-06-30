#!/usr/bin/env bash
# S2-OPS-A-REAL-LAUNCH canary 真号 frozenset 容器内复验 (gate-ON / 真号变更后复验).
#
# 【参数化版】不硬编码槽位数 — 从 real.yaml 的 phone_env 条目动态读期望真号数,
# 抗白名单变更 (colleague 增减时无需改脚本)。魈架构要求 2026-06-30:
#   expected_real_count = real.yaml 里 phone_env 条目数 (不死写 13)
#   expected_frozenset  = expected_real_count + 1 (sentinel)
#   防假阳性门槛         = ENV 注入 == expected_real_count (动态, 非死 13)
#
# 凝光裁定 — dry-run 复验必须验"真实部署注入路径"(env文件→compose passthrough→容器ENV→frozenset),
# 非 mock、非本地 source 旁路。本脚本 docker exec 进 canary backend 容器内跑 canary_whitelist
# 加载逻辑 (读容器真实 ENV + 容器内 real.yaml), 端到端验真号注入链。
#
# 零真号铁律: 只输出 frozenset size / 期望 size / 匹配数 / 掩码(前3****后4)。绝不打印真号值。
#
# 防假阳性 (凝光裁定核心防线): ENV 注入必须 == real.yaml 期望槽位数。
#   未全注入直接 FAIL, 拒绝"真号没配 frozenset 只剩 sentinel 也判 PASS"的退化假阳性。
#
# 前置: REAL_PHONE_* passthrough 已进 compose (PR #369) + 主 tree up.sh canary rebuild (真号进容器)。
#
# usage: bash backend/scripts/canary_real_verify_incontainer.sh [container_name] [real_yaml_path_in_container]
#   container_name              默认 yiluan-canary-backend-1
#   real_yaml_path_in_container 默认 /deploy/canary/whitelist_phones.real.yaml
# exit 0=PASS / 1=FAIL / 2=配置错误

set -uo pipefail
CONTAINER="${1:-yiluan-canary-backend-1}"
REAL_YAML="${2:-/deploy/canary/whitelist_phones.real.yaml}"

if ! docker ps --format '{{.Names}}' | grep -q "^${CONTAINER}$"; then
  echo ">>> 配置错误: 容器 ${CONTAINER} 未运行" >&2
  exit 2
fi

# 容器内复验脚本 (printf 逐行构造, 避 heredoc \n 坑 — 见 MEMORY 反复警示)
PROBE=/tmp/canary_verify_$$.py
printf '%s\n' \
'import os, sys' \
'from app.services import canary_whitelist as cw' \
'REAL_YAML = os.environ.get("VERIFY_REAL_YAML", "/deploy/canary/whitelist_phones.real.yaml")' \
'SENT = "1" + "3800000000"' \
'PLACEHOLDER = "___" + "****" + "____"' \
'def mask(n):' \
'    return n[:3] + "****" + n[-4:] if len(n) == 11 else "***bad***"' \
'# 动态读 real.yaml 的 phone_env 条目名 (= 期望真号槽位, 不硬编码; split 避复杂 regex 转义坑)' \
'names = []' \
'try:' \
'    with open(REAL_YAML, "r", encoding="utf-8") as f:' \
'        for line in f:' \
'            s = line.strip()' \
'            if s.startswith("#") or "phone_env:" not in s:' \
'                continue' \
'            val = s.split("phone_env:", 1)[1].strip().strip(chr(34)).strip(chr(39))' \
'            if val:' \
'                names.append(val)' \
'except FileNotFoundError:' \
'    print(f">>> 配置错误: real.yaml 不在容器 {REAL_YAML}")' \
'    sys.exit(2)' \
'if not names:' \
'    print(f">>> 配置错误: real.yaml 无 phone_env 条目 {REAL_YAML}")' \
'    sys.exit(2)' \
'N = len(names)' \
'print(f"real.yaml phone_env 槽位 (动态读): {N}")' \
'present = [n for n in names if os.environ.get(n, "").strip()]' \
'missing = [n for n in names if not os.environ.get(n, "").strip()]' \
'print(f"ENV 注入: {len(present)}/{N}")' \
'if missing:' \
'    print(f"ENV 缺失(名): {chr(44).join(missing)}")' \
'if len(present) != N:' \
'    print(f">>> 容器内复验: FAIL (ENV 注入 {len(present)}/{N} 非全槽位 — 拒绝假阳性)")' \
'    sys.exit(1)' \
'if hasattr(cw, "reset_for_tests"):' \
'    cw.reset_for_tests()' \
'snap = cw.get_snapshot()' \
'phones = (snap.phones if hasattr(snap, "phones") else snap) if snap is not None else frozenset()' \
'reals = {os.environ.get(n, "").strip() for n in names}' \
'reals = {p for p in reals if p}' \
'expected = reals | {SENT}' \
'miss_fs = reals - phones' \
'overflow = phones - expected' \
'print(f"frozenset size: {len(phones)}")' \
'print(f"expected size: {len(expected)} (={len(reals)} 真号 + 1 sentinel)")' \
'print(f"sentinel in: {chr(89)+chr(69)+chr(83) if SENT in phones else chr(78)+chr(79)}")' \
'print(f"真号匹配: {len(reals)-len(miss_fs)}/{len(reals)}")' \
'ok = True' \
'if miss_fs:' \
'    ok = False' \
'    mn = [n for n in names if os.environ.get(n, "").strip() in miss_fs]' \
'    print(f"FAIL 遗漏: {len(miss_fs)} 真号未进 frozenset, 涉及(名): {chr(44).join(mn)}")' \
'else:' \
'    print(f"OK 无遗漏: {len(reals)} 真号全进 frozenset")' \
'if overflow:' \
'    ok = False' \
'    print(f"FAIL 溢出: {len(overflow)} 期望外号(掩码): {chr(44).join(mask(p) for p in sorted(overflow))}")' \
'else:' \
'    print("OK 无溢出")' \
'if PLACEHOLDER in phones:' \
'    ok = False' \
'    print("FAIL 占位混入: frozenset 含占位 (机制应 skip)")' \
'else:' \
'    print("OK 无占位混入")' \
'if ok and len(phones) == len(expected) and len(reals) == N:' \
'    print(f">>> 容器内复验: PASS ({N} 真号全注入 + frozenset 含且仅含 {N} 真号 + sentinel)")' \
'    sys.exit(0)' \
'else:' \
'    print(">>> 容器内复验: FAIL (见上检测项)")' \
'    sys.exit(1)' \
> "$PROBE"

docker cp "$PROBE" "${CONTAINER}:${PROBE}" >/dev/null
docker exec -w /app -e PYTHONPATH=/app -e VERIFY_REAL_YAML="${REAL_YAML}" "${CONTAINER}" python "${PROBE}"
RC=$?

docker exec "${CONTAINER}" rm -f "${PROBE}" 2>/dev/null
rm -f "${PROBE}"

exit $RC
