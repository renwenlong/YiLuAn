"""PII 脱敏辅助函数。

用于日志、调试输出等场景，避免手机号、身份证等个人信息明文泄漏到日志系统。

使用示例：
    from app.core.pii import mask_phone
    logger.info("SMS sent to %s", mask_phone(phone))
"""
from __future__ import annotations


def mask_phone(phone: str | None) -> str:
    """掩码手机号：保留前 3 + 后 2，中间替换为 *。

    - `13812345678` → `138******78`
    - `+8613812345678` → `+861******78`（前 4 + 后 2，长度 ≥ 10 按同规则）
    - 短号或无效输入：原样返回（但非空仍部分遮蔽以防误用）
    - None / 空字符串：返回空字符串
    """
    if not phone:
        return ""
    s = str(phone)
    n = len(s)
    if n <= 4:
        # 太短无法合理掩码，全部打码
        return "*" * n
    if n <= 8:
        # 保留前 2 + 后 2
        return s[:2] + "*" * (n - 4) + s[-2:]
    # 国内手机（11 位）或带 +86 前缀：保留前 3 + 后 2
    prefix_len = 3
    if s.startswith("+"):
        prefix_len = min(4, n - 3)
    suffix_len = 2
    middle = n - prefix_len - suffix_len
    return s[:prefix_len] + "*" * middle + s[-suffix_len:]


def mask_id_card(id_card: str | None) -> str:
    """掩码身份证号：保留前 4 + 后 4，中间全部 *。"""
    if not id_card:
        return ""
    s = str(id_card)
    n = len(s)
    if n <= 8:
        return "*" * n
    return s[:4] + "*" * (n - 8) + s[-4:]
