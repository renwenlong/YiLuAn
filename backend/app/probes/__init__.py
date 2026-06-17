"""Concrete startup probes registry.

收编现有散点 ``if env in {staging,canary,production}`` / ``if env == "production"``
模式 (AC#5). 任何新增 prod-required asset / config check MUST 走
``@register_startup_probe`` 装饰器, 不允许新加 inline env check
(被 ``scripts/qa/check_no_inline_env_check.py`` lint 哨兵 in PR2 拦截).

每个 probe fn 接受 0 参数, 返 None on pass, raise on fail. probe 失败原文
通过 traceback 暴露 → ``run_all_startup_probes`` log + metric + re-raise.

importing this module triggers probe registration as a side effect; it is
imported once at startup from ``app.main`` (after settings load, before
``run_all_startup_probes``).
"""

from __future__ import annotations

import logging

from app.startup_probes import register_startup_probe

logger = logging.getLogger(__name__)


# ============================================================================
# AC#5 #1: ai_prep_filter (replaces assert_blocklist_loaded_or_raise +
#          settings.ai_blocklist_strict_load gate)
# ============================================================================


@register_startup_probe(
    name="ai_prep_filter_blocklist",
    envs=("staging", "canary", "production"),
)
def probe_ai_prep_filter_blocklist() -> None:
    """Verify prohibited-keywords.yml ships + parses + snapshot non-empty.

    Replaces inline ``settings.ai_blocklist_strict_load`` gate logic in
    ``app/services/ai_prep_filter.py::assert_blocklist_loaded_or_raise``.
    The old fn is kept as a thin wrapper for backward compat (test fixtures
    may still call it explicitly), but app startup now goes through this
    central registry.

    Fail-loud semantics (raises BlocklistStartupError on any of):
      - yml file missing (Dockerfile漏 COPY)
      - snapshot 为空 (parse fail / categories not dict)
      - version 为空字符串 (yml 缺 version 头)

    Refs:
      - S3-BUG-003 (ADR-0048 §4.1/§4.3 关键词过滤是医疗安全哨兵)
      - PR #258 review comment 4676805533 ask 3 (转 fail-loud registry)
    """
    from app.services.ai_prep_filter import (
        _DEFAULT_YML_PATH,
        BlocklistStartupError,
        _cache,
    )

    errors: list[str] = []
    if not _DEFAULT_YML_PATH.exists():
        errors.append(
            f"prohibited-keywords.yml missing at {_DEFAULT_YML_PATH} "
            f"(检查 Dockerfile / build context)"
        )
    snapshot = _cache.snapshot  # 未 load 时 lazy load
    version = _cache.version
    if not snapshot:
        errors.append(
            "blocklist snapshot empty (fail-open detected); "
            "yml 存在但 parse 失败 / categories 不是 dict / 空 yml."
        )
    if not version:
        errors.append("blocklist version 为空字符串 (yml 缺 version 头).")

    if errors:
        joined = "; ".join(errors)
        raise BlocklistStartupError(
            f"AI prep blocklist startup probe FAIL: {joined}. "
            f"Refusing to serve (参考 ADR-0048 §4.1/§4.3, 关键词过滤是医疗安全哨兵)."
        )


# ============================================================================
# AC#5 #2: canary_whitelist (PR #304 反案 #11 复发修复, 收编同 bug pattern)
# ============================================================================


@register_startup_probe(
    name="canary_whitelist_yml",
    envs=("staging", "canary", "production"),
)
def probe_canary_whitelist_yml() -> None:
    """Verify whitelist_phones.yaml ships + parses.

    本 probe 是 PR #304 反案 #11 复发修复的运行时哨兵 — 配合
    ``backend/Dockerfile`` 的 ``COPY deploy/canary/`` 双重防御:
      - Dockerfile COPY 是 build artifact 保证
      - 本 probe 是 startup 运行时 cross-check (Dockerfile 改坏 → 启动即 crash)

    Fail-loud semantics (raises on any of):
      - yml file missing (Dockerfile 漏 COPY)
      - load 后 sentinel 号 13800000000 不在 phones (yml 漂移)

    Refs:
      - PR #302 (S2-OPS-A-CANARY-WHITELIST-LAUNCH AC-2)
      - PR #304 (fix-forward, 反案 #11 复发)
    """
    from app.services.canary_whitelist import (
        _DEFAULT_YML_PATH,
        _WhitelistCache,
    )

    if not _DEFAULT_YML_PATH.exists():
        raise RuntimeError(
            f"canary whitelist yml missing at {_DEFAULT_YML_PATH} "
            f"(检查 Dockerfile COPY deploy/canary/ — 反案 #11)"
        )

    # 用 fresh cache 避免污染 module singleton (生产 lazy load 路径)
    cache = _WhitelistCache()
    cache.load()
    phones = cache._snapshot.phones
    if "13800000000" not in phones:
        raise RuntimeError(
            f"canary whitelist sentinel 13800000000 缺失. phones={phones!r}. "
            f"yml 漂移 / placeholder filter 漂移. yml path: {_DEFAULT_YML_PATH}"
        )


# ============================================================================
# AC#5 #3: SMS provider (替代 legacy 的 per-send inline env check;
#          legacy services/sms.py 已于 PR #333 删除。实际 prod 路径走
#          providers/sms/factory.py, 本 probe 在 startup 一次性验证
#          configured provider 可实例化)
# ============================================================================


@register_startup_probe(
    name="sms_provider_configured",
    envs=("production",),
)
def probe_sms_provider_configured() -> None:
    """Verify ``settings.sms_provider`` is configured + provider class instantiable.

    替代早期 legacy module 中的 per-send runtime env check (该 module
    已于 PR #333 删除)。生产路径走
    ``backend/app/services/providers/sms/factory.py::get_sms_provider()``.

    在 production env 下本 probe 校验:
      - ``settings.sms_provider`` not in {"mock", "", "stub"} (启用真 provider)
      - ``get_sms_provider()`` 不抛 (factory 选 path + 实例化 OK + creds present)
      - provider class != MockSMSProvider (cred 缺失时 factory 会 fallback mock,
        本 probe 显式拒绝 fallback 在 prod 发生)

    Fail-loud → app 拒启 → 不会发生 \"prod 开起来但 OTP 永远不到\" 哑火.

    Refs:
      - 旧散点 ``settings.environment == 'production'`` (legacy module, 已于 PR #333 删除)
      - factory: services/providers/sms/factory.py
    """
    from app.config import settings
    from app.services.providers.sms import get_sms_provider
    from app.services.providers.sms.mock import MockSMSProvider

    sms_provider_name = getattr(settings, "sms_provider", "mock")
    if sms_provider_name in {"mock", "", "stub"}:
        raise RuntimeError(
            f"SMS provider startup probe FAIL: settings.sms_provider="
            f"{sms_provider_name!r} not allowed in production env. "
            f"Configure sms_provider=aliyun (or tencent) in deploy env."
        )

    # 实例化 — 若 creds 缺失, AliyunSMSProvider.__init__ 会 raise ValueError.
    # logging_wrapper 包装不影响实例化.
    provider = get_sms_provider()
    if isinstance(provider, MockSMSProvider):
        raise RuntimeError(
            f"SMS provider startup probe FAIL: get_sms_provider() returned "
            f"MockSMSProvider in production env (factory fallback triggered, "
            f"creds likely missing). settings.sms_provider="
            f"{sms_provider_name!r}. Verify SMS_ACCESS_KEY/SMS_ACCESS_SECRET."
        )


# ============================================================================
# AC#5 #4: jwt_secret_key (额外发现 — config.py 默认值容易 prod 误用)
# ============================================================================


@register_startup_probe(
    name="jwt_secret_key_changed",
    envs=("staging", "canary", "production"),
)
def probe_jwt_secret_key_changed() -> None:
    """Verify ``settings.jwt_secret_key`` 已改 (不是默认 staging fallback value).

    config.py 里 ``jwt_secret_key`` 默认是已知 fallback；
    若 deploy 时漏改 env, JWT secret 是已知值 → 所有 token 可被攻击者伪造.
    本 probe 在 startup 哨兵, 漏改即 app 拒启.

    Refs:
      - config.py:26 (默认 jwt_secret_key)
      - 安全 hardening common 模式 (12factor §III config)
    """
    from app.config import settings

    DEFAULT_KNOWN_SECRETS = {
        "dev-secret-key-change-in-production",
        "staging-secret-key-change-in-production",
    }
    if settings.jwt_secret_key in DEFAULT_KNOWN_SECRETS:
        raise RuntimeError(
            "JWT secret key startup probe FAIL: settings.jwt_secret_key 仍是"
            f" 默认已知值 {settings.jwt_secret_key!r}. "
            f"必须在 deploy env 设 JWT_SECRET_KEY 为强随机值. "
            f"否则所有 JWT token 可被攻击者伪造."
        )
    if len(settings.jwt_secret_key) < 32:
        raise RuntimeError(
            f"JWT secret key startup probe FAIL: jwt_secret_key 长度 "
            f"{len(settings.jwt_secret_key)} < 32 chars. 建议 >=64 chars "
            f"(openssl rand -hex 32)."
        )


# ============================================================================
# AC#1: redis_required_for_complaint_rate
#       (S3-OPS-COMPLAINT-RATE-REDIS-REQUIRED-PROBE — replaces silent inproc
#       fallback in app/services/readonly_complaint_rate_store.py, ADR-0053
#       §AC#4 协议层兜底, PR #308 r1 review follow-up)
# ============================================================================


@register_startup_probe(
    name="redis_required_for_complaint_rate",
    envs=("staging", "canary", "production"),
)
async def probe_redis_required_for_complaint_rate() -> None:
    """Verify redis 可用且 ZSET op (zadd/zrangebyscore) 实际跑得通.

    背景: ``app/services/readonly_complaint_rate_store.py`` 有 in-process
    list fallback (class var ``_inproc_samples``). prod multi-uvicorn-worker
    部署下, PM POST 注入到 worker-A → cron 跑 worker-B → 永远 0 sample
    → grace None → design §AC#3 #4 客诉率 threshold 检查永久 grace bypass
    (设计的 NOGO gate 实质失效).

    本 probe 在 startup 强制校验 redis 可用 + ZSET op 实际可调:
      - redis None / 连不上 → raise (app 拒启)
      - zadd / zrangebyscore raise → raise (app 拒启)
      - sentinel key 60s 自清, 不污染业务 key space

    AC#3: fail-loud, 不允许 try/except 吞.

    Refs:
      - ADR-0053 §AC#4 (complaint rate manual injection)
      - PR #308 r1 review (silent fail 风险 disclose)
      - 反案 #25 (协议层强制 env-dependent invariant, 散点 env check 禁止)
      - app/services/readonly_complaint_rate_store.py:49 (_inproc_samples)
    """
    import uuid

    from app.core.redis import init_redis

    # 独立 client (probe 阶段 app.state.redis 还没初始化, 见 main.py 顺序).
    # 跑完 close, 不污染 lifespan.
    sentinel_key = "yiluan:probe:complaint_rate:sentinel"
    sentinel_member = f"probe-{uuid.uuid4().hex}"
    sentinel_score = 1.0

    redis_client = None
    try:
        # init_redis 本身在 try 内, 其 raise 也走 AC#3 fail-loud 路径
        redis_client = init_redis()
        # 写: 校验 ZSET zadd 可用
        await redis_client.zadd(sentinel_key, {sentinel_member: sentinel_score})
        # 读: 校验 ZSET zrangebyscore 可用 (cron 实际查询路径)
        members = await redis_client.zrangebyscore(
            sentinel_key,
            min=0,
            max=2.0,
            withscores=False,
        )
        if sentinel_member not in (members or []):
            raise RuntimeError(
                f"redis_required_for_complaint_rate probe FAIL: "
                f"sentinel zadd 写入成功但 zrangebyscore 读不回 "
                f"(member={sentinel_member!r} not in {members!r}). "
                f"redis op 异常或 cluster 不一致."
            )
        # 清理: TTL 兜底, 不留 trash (60s 即自动 expire, 即使 EXPIRE 失败也容忍)
        try:
            await redis_client.expire(sentinel_key, 60)
        except Exception:  # noqa: BLE001 - cleanup best-effort
            pass
    except RuntimeError:
        # AC#3: re-raise 自己 raise 的 (fail-loud, 不吞)
        raise
    except Exception as exc:
        # 任何 redis op 异常 (ConnectionError / TimeoutError / ResponseError
        # / AttributeError on inproc fake / etc) → raise RuntimeError
        # 包一层, 让 traceback 清楚是 probe 失败 (AC#3 fail-loud).
        raise RuntimeError(
            f"redis_required_for_complaint_rate probe FAIL: redis op "
            f"raised {type(exc).__name__}: {exc}. "
            f"complaint rate store ZSET 不可用, design §AC#3/#4 客诉率"
            f" gate 在 prod inproc fallback 下永久 grace bypass. "
            f"必须修 redis 连接."
        ) from exc
    finally:
        # close client (不影响 app.state.redis 后续 init)
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:  # noqa: BLE001 - cleanup best-effort
                pass
