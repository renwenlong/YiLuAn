"""Abstract base class + DTOs for SMS providers (P0-2, Action #2).

Mirrors the structure of ``app.services.providers.payment``: a thin
abstract API plus dataclasses so callers (and tests) don't depend on
any concrete vendor SDK.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class SMSResult:
    """Outcome of an SMS send call.

    The shape is intentionally flat / JSON-serialisable so it can be
    returned from API handlers, logged, or surfaced to monitoring.

    Fields
    ------
    ok :
        ``True`` if the message was accepted by the provider (or by the
        mock). ``False`` for any structured failure.
    code :
        Stable error code. ``"ok"`` on success. Failure values include
        ``"rate_limited"`` (caller hit the per-phone window) and
        ``"provider_error"`` (downstream PSP returned non-OK).
    message :
        Human-readable description; safe to surface to logs (PII-masked
        upstream).
    provider :
        Name of the concrete provider (``"mock"``, ``"aliyun"``, ...).
    extra :
        Provider-specific metadata. Kept opaque on purpose.
    """

    ok: bool
    code: str = "ok"
    message: str = ""
    provider: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


class SMSProvider:
    """Abstract base for SMS providers.

    Subclasses **must** override :meth:`send_otp` and :meth:`send_notification`.
    Both are async because real PSP calls are network-bound.
    """

    name: str = "base"

    async def send_otp(
        self,
        phone: str,
        code: str,
        template_id: str | None = None,
    ) -> SMSResult:
        """Send a one-time-password SMS.

        Parameters
        ----------
        phone :
            E.164 or bare CN mobile number. Must NEVER appear in logs
            in plaintext — callers/providers must mask via
            :func:`app.core.pii.mask_phone` (or the SMS-specific
            :func:`mask_phone_sms` helper).
        code :
            Numeric OTP. Treated as secret; never log.
        template_id :
            Optional vendor template id override.
        """
        raise NotImplementedError

    async def send_notification(
        self,
        phone: str,
        template_id: str,
        params: dict[str, Any] | None = None,
    ) -> SMSResult:
        """Send a transactional / marketing SMS via a configured template."""
        raise NotImplementedError


def mask_phone_sms(phone: str | None) -> str:
    """SMS-log-friendly phone mask: keep first 3 + last 4, mask middle 4.

    Examples::

        13800010001  -> 138****0001
        +8613800010001 -> +86138****0001
        ""           -> ""

    Distinct from :func:`app.core.pii.mask_phone` (which masks all
    middle digits). This shorter form is the conventional "phone book"
    style used in OTP audit logs and matches the assertion style used
    in the SMS test suite.
    """
    if not phone:
        return ""
    s = str(phone)
    plus_prefix = ""
    digits = s
    # Preserve a leading "+CC" prefix verbatim. We assume the trailing 11
    # digits are the actual mobile number (CN convention). For non-CN
    # numbers this still produces a privacy-preserving output, just with
    # the country code visible.
    if s.startswith("+") and len(s) >= 12:
        # split off everything except the trailing 11 digits as the CC.
        plus_prefix = s[: len(s) - 11]
        digits = s[len(s) - 11 :]
    n = len(digits)
    if n < 7:
        # Too short for 3+4 — partial mask, never plaintext.
        if n <= 2:
            return plus_prefix + "*" * n
        return plus_prefix + digits[:1] + "*" * (n - 2) + digits[-1:]
    head = digits[:3]
    tail = digits[-4:]
    return f"{plus_prefix}{head}****{tail}"
