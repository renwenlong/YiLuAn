"""S2-OPS-A-CANARY-WHITELIST-LAUNCH AC-2 follow-up: yml asset-presence test.

任务: PR #302 (bafe22c) merge 后, 魈 review 时撞反案 #11 同模式坑 ——
全部 12 unit/endpoint test 用 ``tmp_path`` / ``monkeypatch`` 跑, 0 test 不 mock
验证 ``_DEFAULT_YML_PATH.exists() is True``, 单元覆盖 100% 但根本没暴露
build artifact 缺失.

背景 (反案 #11 同模式 S3-BUG-003):
backend Docker image 漏 COPY ``deploy/canary/`` →
``whitelist_phones.yaml`` 在容器内永远 not found,
``canary_whitelist._WhitelistCache.load()`` fail-closed empty,
``settings.canary_whitelist_enabled=True`` 一开则:
  - aggregator 前置过滤 + 后端 ABAC 兜底 双层都视 phone 不在白名单
  - F2 入口对所有 (含团队 + 帝君指派同事) 返 403
  - SHARE_F2_CANARY_NOT_WHITELISTED 全员触发
  - 灰度业务 100% 失效, 帝君 06-08 拍 A 选项 "内部白名单 10% mock" 完全 dead

修复:
  - backend/Dockerfile 加 ``COPY deploy/canary/ /deploy/canary/`` (随 image ship)
  - 本 test 不 mock 验证 ``_DEFAULT_YML_PATH`` 存在 + 真 load 后 snapshot 含
    sentinel 号 (13800000000), 任一漂移即 CI fail

本 test 模仿 ``backend/tests/integration/test_blocklist_yml_present.py`` (S3-BUG-003
同 bug pattern fix 留下的范本 — 反案 #11 sentinel SECRET_CANARY_YML_PRESENT_42).
"""

from __future__ import annotations

from app.services.canary_whitelist import (
    _DEFAULT_YML_PATH,
    _PLACEHOLDER_PREFIXES,
    _WhitelistCache,
    get_snapshot,
    is_whitelisted,
    reload,
)

# Sentinel string for grep / rg 防误删 (反案 #11 + #15 SOP).
_SECRET_CANARY_YML_PRESENT_42 = "SECRET_CANARY_YML_PRESENT_42_DO_NOT_LEAK"


class TestCanaryWhitelistYmlPresent:
    """canary whitelist yml 必须随 backend image 一起 ship.

    反案 #11 (S3-BUG-003) 同 bug 模式: ``Path(__file__).resolve().parents[3]``
    在容器内解析到 ``/``, 故 yml 必须 COPY 到 ``/deploy/canary/``.
    """

    def test_default_yml_path_exists(self) -> None:
        """assert SoT yml 存在: 不存在即 Dockerfile / build context 漏 COPY.

        本 test 是 PR #302 follow-up fix 的根本验证 —
        如该 test fail, 检查 backend/Dockerfile 是否 COPY deploy/canary/
        + deploy/docker-compose.yml build.context 是否在 repo 根.
        """
        assert _DEFAULT_YML_PATH.exists(), (
            f"whitelist_phones.yaml 必须随 backend image 一起 ship. "
            f"Expected at: {_DEFAULT_YML_PATH}. "
            f"如该测试 fail, 检查 backend/Dockerfile 是否 COPY deploy/canary/ "
            f"+ deploy/docker-compose.yml build.context 是否在 repo 根. "
            f"sentinel={_SECRET_CANARY_YML_PRESENT_42}"
        )

    def test_default_yml_path_is_file(self) -> None:
        """assert SoT yml 是文件 (不是目录或 symlink dangling)."""
        assert _DEFAULT_YML_PATH.is_file(), (
            f"{_DEFAULT_YML_PATH} exists but is not a regular file "
            f"(possibly broken symlink or directory)."
        )

    def test_real_load_marks_cache_loaded(self) -> None:
        """assert 真 yml load 后 cache 已标记 loaded (非 fail-closed first-call).

        本 test 用 fresh _WhitelistCache 避免污染 module singleton.
        """
        cache = _WhitelistCache()
        cache.load()  # 走 _DEFAULT_YML_PATH 真路径
        assert cache._loaded, "cache should be marked loaded after load()"

    def test_real_load_sentinel_phone_present(self) -> None:
        """assert 真 yml load 后 sentinel 号 13800000000 在 snapshot 里.

        当前 yml 团队 5 个 + 同事 5 个全是 __PENDING_*__ placeholder,
        服务按 _PLACEHOLDER_PREFIXES 跳过 → snapshot.phones = {"13800000000"}
        (唯一非 placeholder). 后续 PM 收齐真号填充后 phones 数量增长,
        但 sentinel 永久保留 (yml 注释 "本地 e2e / smoke 用, 永久保留").

        如本 test fail, 可能原因:
          - yml 漂移: sentinel 号被误删
          - placeholder prefix 配置漂移: _PLACEHOLDER_PREFIXES 改了
          - _extract_phones 逻辑漂移: section 名改了 / placeholder 跳过逻辑改了
          - 路径漂移: _DEFAULT_YML_PATH 解析错 (上面 path_exists test 兜底)
        """
        cache = _WhitelistCache()
        cache.load()
        phones = cache._snapshot.phones
        assert "13800000000" in phones, (
            f"sentinel phone 13800000000 不在 snapshot.phones 里: {phones}. "
            f"可能 yml 漂移 (sentinel 误删) / placeholder 配置漂移. "
            f"yml path: {_DEFAULT_YML_PATH}"
        )

    def test_real_load_excludes_placeholders(self) -> None:
        """assert load 后 placeholder 号没漏进 phones.

        __PENDING_* / __PLACEHOLDER_* 是占位符, 不能作为真号判 whitelist.
        如该 test fail, _extract_phones 的 placeholder 过滤 broke.
        """
        cache = _WhitelistCache()
        cache.load()
        phones = cache._snapshot.phones
        for phone in phones:
            for prefix in _PLACEHOLDER_PREFIXES:
                assert not phone.startswith(prefix), (
                    f"phone {phone!r} starts with placeholder prefix {prefix!r}; "
                    f"_extract_phones placeholder filter is broken."
                )

    def test_real_load_loaded_from_matches_default_path(self) -> None:
        """assert snapshot.loaded_from = str(_DEFAULT_YML_PATH).

        observability: ops 看 /admin 接口里 snapshot.loaded_from 字段时,
        应能确认数据从 SoT 路径来, 不是从 tmp_path 测试残留.
        """
        cache = _WhitelistCache()
        cache.load()
        assert cache._snapshot.loaded_from == str(_DEFAULT_YML_PATH), (
            f"snapshot.loaded_from {cache._snapshot.loaded_from!r} "
            f"!= str(_DEFAULT_YML_PATH) {str(_DEFAULT_YML_PATH)!r}"
        )

    def test_module_singleton_lazy_load_via_is_whitelisted(self) -> None:
        """assert module singleton 通过 is_whitelisted() 触发 lazy load 后能命中.

        与 ai_prep_filter 不同, canary_whitelist 不在 import-time eager load
        (module 末尾仅 ``_cache = _WhitelistCache()``, 无 ``_cache.load()`` 调用).
        首次 is_whitelisted / get_snapshot 时由 ``snapshot()`` 内 lazy load.

        本 test 直接走 module-level is_whitelisted, 模拟生产 callers 路径:
        如返 False, 即生产 fail-closed → 全员 403.
        """
        # Force fresh module state for this test (avoid order-dependence)
        from app.services.canary_whitelist import reset_for_tests

        reset_for_tests()
        try:
            assert is_whitelisted("13800000000") is True, (
                "module singleton 通过 is_whitelisted lazy load 后 sentinel 号"
                " 不在白名单. 可能 _DEFAULT_YML_PATH 漂移 / placeholder filter 漂移. "
                f"sentinel={_SECRET_CANARY_YML_PRESENT_42}"
            )
            # get_snapshot 同样路径 verify
            snap = get_snapshot()
            assert "13800000000" in snap.phones
            assert snap.loaded_from == str(_DEFAULT_YML_PATH)
        finally:
            reset_for_tests()  # 清干净避免污染后续测试

    def test_reload_with_default_path_works(self) -> None:
        """assert 显式 reload() 也能加载 SoT yml (admin 热重载路径).

        admin 端日后会有 ``POST /admin/canary/whitelist/reload`` 端点,
        路径调用 ``canary_whitelist.reload()`` 不带参数, 走默认路径.
        本 test 覆盖这条 lift-and-shift 路径.
        """
        from app.services.canary_whitelist import reset_for_tests

        reset_for_tests()
        try:
            reload()  # no arg → _DEFAULT_YML_PATH
            snap = get_snapshot()
            assert (
                "13800000000" in snap.phones
            ), "reload() 后 sentinel 号不在 snapshot, default path load broke"
        finally:
            reset_for_tests()
