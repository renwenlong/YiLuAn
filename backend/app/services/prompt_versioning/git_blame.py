"""Prompt versioning utilities: git blame + DB双锁 (ADR-0048 §5).

PromptVersion 设计哲学：
- **git 端**: prompt 文件入 `docs/ai-prompts/<axis>/<version>/*.md`,
  通过 git tag 标定版本（如 `prompt-s3-prep-v1.0.0`）
- **DB 端**: `prompt_versions` 表 (path, commit_sha, content_hash, ...)
- **双锁意义**: 任一缺失 fail-fast — 启动时跑校验, 防止 db 记录指向
  已被 rebase / 删除 的 git commit。

本模块只暴露 ``git_blame_commit`` 一个纯函数, 不入 ORM / 不写 IO,
便于单测 + 在 startup hook 中复用 (见 ``app/main.py`` lifespan)。

**为何不用 GitPython?**
- GitPython 给整个 backend image 加 ~8MB pure-python deps
- 我们只用一处 `git log -n 1 --format=%H -- <path>`, subprocess 30 行
  就能搞定, 引依赖不划算
- ADR-0048 §5.2 已明示 "subprocess, 不引 GitPython runtime dep"
"""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

# git commit SHA-1 = 40 hex chars (lowercase). 兼容 short hash 7~40 位
# 但 git log %H 永远返 full 40 位, 校验也按 40 位严格匹配。
COMMIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")

# subprocess 默认 timeout (s) — git log 应是亚秒级, 5s 足够防 hang
_GIT_TIMEOUT_SECONDS = 5


class GitBlameError(RuntimeError):
    """`git_blame_commit` 失败的统一错误类型。

    场景:
    - git 二进制找不到 (容器最小 image 没装 git)
    - 不在 git 仓库内 (CI ephemeral checkout)
    - path 不存在或从未被 git 追踪
    - subprocess timeout / 非零退出
    """


def git_blame_commit(
    path: str | Path,
    *,
    repo_root: str | Path | None = None,
    git_bin: str | None = None,
) -> str:
    """返回 ``path`` 文件最后一次被 commit 的 40 位 SHA。

    Args:
        path: 仓库内文件路径 (相对 ``repo_root`` 或绝对)。
        repo_root: 显式指定 git 仓库根目录; 默认 None = 用 path 推导
            (subprocess 在 path 父目录跑, git 自动 walk-up 找 .git)。
        git_bin: git 可执行路径; 默认 None = 用 ``shutil.which('git')``。
            注入点便于单测 / 容器内 git 在非 PATH 位置时显式指定。

    Returns:
        40 字符小写十六进制 commit SHA。

    Raises:
        GitBlameError: git 二进制缺失 / 仓库无效 / path 未被追踪 /
            timeout / 输出格式非法 (非 40-hex)。

    Example:
        >>> git_blame_commit("docs/ai-prompts/s3-prep/v1.0.0/system_prompt.md")
        '9f9c84b3d2e1...40字符'
    """
    git_bin = git_bin or shutil.which("git")
    if not git_bin:
        raise GitBlameError(
            "git 二进制找不到 (PATH 中无 git, 容器 image 可能未装 git)"
        )

    path = Path(path)
    cwd = Path(repo_root) if repo_root else (path.parent if path.parent != Path("") else Path.cwd())

    cmd = [git_bin, "log", "-n", "1", "--format=%H", "--", str(path)]
    try:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise GitBlameError(
            f"git log timeout (>{_GIT_TIMEOUT_SECONDS}s): {cmd}"
        ) from exc
    except FileNotFoundError as exc:
        # git_bin 路径无效 (shutil.which 给的路径已被删 / 不可执行)
        raise GitBlameError(f"git 二进制不可执行: {git_bin}") from exc

    if result.returncode != 0:
        raise GitBlameError(
            f"git log 非零退出 (rc={result.returncode}): "
            f"stderr={result.stderr.strip()!r} cwd={cwd}"
        )

    sha = result.stdout.strip()
    if not sha:
        # git log 成功退出但无输出 = path 未被 git 追踪
        raise GitBlameError(
            f"path 未被 git 追踪 (git log 0 output): {path} (cwd={cwd})"
        )

    if not COMMIT_SHA_RE.match(sha):
        # 防御: 万一 git 输出格式被劫持 / 编码污染
        raise GitBlameError(
            f"git log 输出非 40-hex SHA: {sha!r} (cmd={cmd})"
        )

    return sha
