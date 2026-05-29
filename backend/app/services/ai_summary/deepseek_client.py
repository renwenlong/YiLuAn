"""[S2-DEV-005] DeepSeek chat completion client (cost-aware, outbound-wrapped).

Why a thin custom client instead of ``openai`` SDK?
- DeepSeek's API is OpenAI-compatible **except for billing**: pricing is
  per-token, denominated in yuan, model-dependent. We do the cost math
  ourselves here so the budget guard can see fractional-fen precision.
- The official SDK pulls in a heavy dependency tree we don't need.

Reliability
-----------
Wrapped in :func:`outbound_call` so HTTP timeouts / 5xx / connect errors
go through the existing retry + circuit-breaker layer (ADR-0026r1, same
treatment as Aliyun/WeChat providers).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

import httpx

from app.config import settings
from app.utils.outbound import (
    NonRetryableError,
    RetryableError,
    classify_httpx_exception,
    outbound_call,
)

logger = logging.getLogger("app.services.ai_summary.deepseek_client")

DEEPSEEK_PROVIDER = "deepseek"


@dataclass(frozen=True)
class DeepSeekChatResult:
    """Result envelope for a single chat completion call."""

    content: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_yuan: Decimal  # 4-decimal precision (matches AIDigest.cost_yuan)
    truncated: bool = False  # set True when caller hit per-order cap

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


def estimate_cost_yuan(prompt_tokens: int, completion_tokens: int) -> Decimal:
    """Cost = (in/1000 * in_price) + (out/1000 * out_price).

    Rounded HALF_UP to 4 decimal places — matches AIDigest schema.
    """
    in_price = Decimal(str(settings.deepseek_price_input_per_1k_yuan))
    out_price = Decimal(str(settings.deepseek_price_output_per_1k_yuan))
    cost = (
        Decimal(prompt_tokens) / Decimal("1000") * in_price
        + Decimal(completion_tokens) / Decimal("1000") * out_price
    )
    return cost.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def estimate_max_completion_tokens_for_budget(
    prompt_tokens: int, per_order_budget_yuan: Decimal
) -> int:
    """How many completion tokens can we afford given the per-order cap?

    Solve for completion_tokens given a fixed budget and known prompt cost.
    Returns 0 if the prompt alone already exceeds the cap.
    """
    in_price = Decimal(str(settings.deepseek_price_input_per_1k_yuan))
    out_price = Decimal(str(settings.deepseek_price_output_per_1k_yuan))
    prompt_cost = Decimal(prompt_tokens) / Decimal("1000") * in_price
    remaining = per_order_budget_yuan - prompt_cost
    if remaining <= 0 or out_price <= 0:
        return 0
    # tokens = remaining / (out_price / 1000)
    tokens = (remaining / out_price * Decimal("1000")).to_integral_value(rounding="ROUND_DOWN")
    return max(0, int(tokens))


@outbound_call(
    provider=DEEPSEEK_PROVIDER,
    timeout=settings.deepseek_timeout_seconds,
    max_retries=settings.deepseek_max_retries,
)
async def chat_completion(
    *, prompt: str, max_tokens: int, system: str | None = None
) -> DeepSeekChatResult:
    """One DeepSeek chat completion. Caller MUST pre-cap ``max_tokens``."""
    api_key = settings.deepseek_api_key
    if not api_key:
        # Misconfig is a NonRetryableError: don't waste CB budget retrying.
        raise NonRetryableError("DEEPSEEK_API_KEY is not configured")

    payload = {
        "model": settings.deepseek_model,
        "messages": (
            [{"role": "system", "content": system}] if system else []
        )
        + [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
        "temperature": 0.3,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = settings.deepseek_base_url.rstrip("/") + "/v1/chat/completions"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise classify_httpx_exception(exc) from exc

    if resp.status_code >= 500 or resp.status_code in (408, 429):
        raise RetryableError(
            f"DeepSeek {resp.status_code}: {resp.text[:200]}"
        )
    if resp.status_code >= 400:
        raise NonRetryableError(
            f"DeepSeek {resp.status_code}: {resp.text[:200]}"
        )

    try:
        data = resp.json()
        choice = data["choices"][0]
        content = (choice.get("message") or {}).get("content") or ""
        finish_reason = choice.get("finish_reason") or ""
        usage = data.get("usage") or {}
        prompt_tokens = int(usage.get("prompt_tokens") or 0)
        completion_tokens = int(usage.get("completion_tokens") or 0)
        model = data.get("model") or settings.deepseek_model
    except (KeyError, ValueError, TypeError) as exc:
        raise NonRetryableError(f"DeepSeek response shape unexpected: {exc}") from exc

    return DeepSeekChatResult(
        content=content,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        cost_yuan=estimate_cost_yuan(prompt_tokens, completion_tokens),
        truncated=(finish_reason == "length"),
    )


__all__ = [
    "DEEPSEEK_PROVIDER",
    "DeepSeekChatResult",
    "chat_completion",
    "estimate_cost_yuan",
    "estimate_max_completion_tokens_for_budget",
]
