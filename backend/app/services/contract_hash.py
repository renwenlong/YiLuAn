"""Contract hash + canonical order snapshot (S3-DEV-001-CONTRACT-HASH / ADR-0046 §3.2).

# Purpose

Generate a SHA-256 hash that binds a rendered contract PDF to a frozen
snapshot of the order's commercial facts (price, schedule, parties,
patient pseudonym, template version). The pair ``(contract_hash,
hash_inputs_snapshot)`` is captured **once at commit time**: once the
hash is computed, the snapshot is persisted alongside it so the hash
can be re-verified later even after the user edits their profile / the
template version bumps / the service package price changes.

# Why a snapshot — not a live recompute

If we recomputed the hash from the live ``Order`` row each verification,
any of these would silently break a valid contract:

- user renames their account
- companion phone number changes
- service package price bumps
- ContractTemplate version bumps

The snapshot is the contract's **authoritative input** for hash
re-verification. Production reads ``service_contracts.hash_inputs`` (a
JSONB column owned by S3-DEV-001-CONTRACT-DOMAIN) and feeds it back
into ``recompute_contract_hash(snapshot, template_version)`` — see
:func:`recompute_contract_hash`.

# Canonical JSON contract (ADR-0046 §3.2 — strict)

Three parameters are pinned because *any* drift in JSON serialization
flips the hash and invalidates every contract issued under the old
format:

- ``sort_keys=True`` — alphabetic key order, independent of insertion
- ``ensure_ascii=False`` — preserve UTF-8 (Chinese names stay readable
  in the JSONB column for forensic audit)
- ``separators=(",", ":")`` — strip *all* whitespace; default would
  insert spaces and a regression in Python's json module would silently
  alter every hash

# Pseudonym hash — independent salt

``patient_pseudonym_hash = SHA-256(name + last4_id_card + salt)``.

Two non-obvious constraints:

1. **Independent env**: ``CONTRACT_PSEUDONYM_SALT`` is **not**
   ``PII_HASH_SALT`` (cert-image / share-OTP). If the contract salt
   leaks, share-OTP / cert images stay safe; if PII_HASH_SALT leaks,
   contract pseudonyms stay safe. ADR-0046 §3.2.
2. **Last-4 ID, not full**: full ID-card is PII; last-4 is sufficient
   entropy when combined with full name + the independent salt. The
   plaintext ID-card never enters the hash path.

# Out of scope (delegated downstream)

This module is a **pure** function set. It does **not**:

- query the database (caller passes structured args, see signature)
- persist anything (S3-DEV-001-CONTRACT-DOMAIN owns
  ``service_contracts.hash_inputs`` JSONB column + Alembic migration +
  immutable_fields trigger)
- render the contract PDF (S3-DEV-001-CONTRACT-DOMAIN orchestrates)
- decide template version (caller passes the active version)

This lets the hash logic stay unit-testable with zero DB / Azure / HTTP
dependencies, and lets CONTRACT-DOMAIN do the DB schema + state
machine in one atomic Alembic migration.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, Mapping

from app.config import settings

logger_name = __name__

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SHA256_HEX_LEN = 64
"""Length of a SHA-256 hex digest (64 chars)."""

_HASH_INPUTS_REQUIRED_KEYS = frozenset(
    {
        "order_id",
        "amount_cny",
        "service_package_id",
        "scheduled_at",
        "patient_pseudonym_hash",
        "companion_id",
        "template_version",
    }
)
"""Keys ADR-0046 §3.2 requires in every ``hash_inputs_snapshot``.

Drift here (adding/removing a key) flips every contract's hash on
recompute, so the set is pinned + checked by
:func:`_assert_snapshot_shape`.
"""


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class ContractHashGenerationError(ValueError):
    """Raised when contract hash generation fails for a deterministic reason.

    Caller surface (ContractService) translates this into the
    ``generation_failed`` contract status (ADR-0046 §3.4 compensation).
    """


class ContractPseudonymSaltMissingError(ContractHashGenerationError):
    """Raised when ``CONTRACT_PSEUDONYM_SALT`` env is unset / empty.

    Dev default is empty (see ``settings.contract_pseudonym_salt``).
    Production deployments **must** set it to a high-entropy random
    string distinct from ``PII_HASH_SALT``.
    """


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractHashResult:
    """Result of :func:`generate_contract_hash_at_commit_time`.

    Attributes:
        contract_hash: SHA-256 hex (64 chars) bound to the snapshot.
        hash_inputs_snapshot: Dict literally passed to canonical JSON;
            caller (CONTRACT-DOMAIN) writes this into
            ``service_contracts.hash_inputs`` JSONB column verbatim.
    """

    contract_hash: str
    hash_inputs_snapshot: dict[str, Any]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _canonical_json(payload: Mapping[str, Any]) -> str:
    """ADR-0046 §3.2 canonical JSON: sort_keys + utf-8 + no whitespace.

    Pinned parameters; any drift here invalidates every contract.
    """
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _assert_snapshot_shape(snapshot: Mapping[str, Any]) -> None:
    """Sentinel: snapshot has exactly the ADR-0046 §3.2 required keys.

    Extra keys are rejected too — adding a field silently to one caller
    while leaving CONTRACT-DOMAIN's schema unchanged would create
    contracts whose hash can never be re-verified after a future
    schema migration.
    """
    keys = set(snapshot.keys())
    missing = _HASH_INPUTS_REQUIRED_KEYS - keys
    extras = keys - _HASH_INPUTS_REQUIRED_KEYS
    if missing or extras:
        parts: list[str] = []
        if missing:
            parts.append(f"missing={sorted(missing)}")
        if extras:
            parts.append(f"unexpected={sorted(extras)}")
        raise ContractHashGenerationError(f"hash_inputs_snapshot shape drift: {'; '.join(parts)}")


def _get_pseudonym_salt() -> str:
    salt = (settings.contract_pseudonym_salt or "").strip()
    if not salt:
        raise ContractPseudonymSaltMissingError(
            "CONTRACT_PSEUDONYM_SALT is unset; production must set a "
            "high-entropy random string distinct from PII_HASH_SALT."
        )
    return salt


def _to_iso8601_utc(value: datetime | date | str) -> str:
    """Normalize ``scheduled_at`` to ISO-8601 UTC string.

    Accept:
    - ``datetime`` (tz-aware) → ``.astimezone(utc).isoformat()``
    - ``datetime`` (naive) → assume UTC (loud warning would be added in
      a future PR; for now we treat as UTC since the codebase stores
      ``created_at`` etc. with ``timezone.utc`` already)
    - ``date`` → midnight UTC
    - ``str`` → trust caller's ISO-8601 string (validated by tests)
    """
    if isinstance(value, str):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, date):
        # combine date + midnight UTC
        return datetime.combine(value, time(0, 0), tzinfo=timezone.utc).isoformat()
    raise ContractHashGenerationError(
        f"scheduled_at must be datetime/date/str, got {type(value).__name__}"
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def compute_patient_pseudonym_hash(
    *,
    patient_name: str,
    id_card_last4: str,
) -> str:
    """SHA-256(name || last4 || CONTRACT_PSEUDONYM_SALT) — hex digest.

    Args:
        patient_name: Full name as it appears on the contract; whitespace
            is **not** stripped (caller is responsible for normalization,
            because contract presentation rules may differ from hash
            inputs — e.g. trailing zero-width chars).
        id_card_last4: Last 4 characters of the patient's national ID
            card number. Full ID-card never enters this path.

    Raises:
        ContractPseudonymSaltMissingError: ``CONTRACT_PSEUDONYM_SALT``
            env is unset.
        ContractHashGenerationError: arg validation failure.
    """
    if not patient_name:
        raise ContractHashGenerationError("patient_name must be non-empty")
    if not id_card_last4 or len(id_card_last4) != 4:
        raise ContractHashGenerationError(
            f"id_card_last4 must be exactly 4 chars, got {len(id_card_last4)}"
        )
    salt = _get_pseudonym_salt()
    payload = f"{patient_name}|{id_card_last4}|{salt}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def build_hash_inputs_snapshot(
    *,
    order_id: str,
    amount_cny: int,
    service_package_id: str,
    scheduled_at: datetime | date | str,
    patient_pseudonym_hash: str,
    companion_id: str,
    template_version: str,
) -> dict[str, Any]:
    """Construct the canonical hash_inputs dict.

    Returns a fresh dict suitable for JSONB persistence (caller, i.e.
    CONTRACT-DOMAIN, writes into ``service_contracts.hash_inputs`` and
    later re-feeds into :func:`recompute_contract_hash` for verification).

    All args are validated; on success the dict is shape-checked by
    :func:`_assert_snapshot_shape` so we never persist a malformed row.
    """
    if not order_id:
        raise ContractHashGenerationError("order_id required")
    if not isinstance(amount_cny, int) or amount_cny <= 0:
        raise ContractHashGenerationError(
            f"amount_cny must be positive int (分单位), got {amount_cny!r}"
        )
    if not service_package_id:
        raise ContractHashGenerationError("service_package_id required")
    if not companion_id:
        raise ContractHashGenerationError("companion_id required (合同必须在 accepted 状态后生成)")
    if not template_version:
        raise ContractHashGenerationError("template_version required")
    if not patient_pseudonym_hash or len(patient_pseudonym_hash) != SHA256_HEX_LEN:
        raise ContractHashGenerationError(
            f"patient_pseudonym_hash must be SHA-256 hex ({SHA256_HEX_LEN} chars)"
        )

    snapshot: dict[str, Any] = {
        "order_id": order_id,
        "amount_cny": amount_cny,
        "service_package_id": service_package_id,
        "scheduled_at": _to_iso8601_utc(scheduled_at),
        "patient_pseudonym_hash": patient_pseudonym_hash,
        "companion_id": companion_id,
        "template_version": template_version,
    }
    _assert_snapshot_shape(snapshot)
    return snapshot


def _hash_from_snapshot(snapshot: Mapping[str, Any], template_version: str) -> str:
    """SHA-256(template_version + '|' + canonical_json(snapshot)) — hex."""
    _assert_snapshot_shape(snapshot)
    payload = f"{template_version}|{_canonical_json(snapshot)}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def generate_contract_hash_at_commit_time(
    *,
    order_id: str,
    amount_cny: int,
    service_package_id: str,
    scheduled_at: datetime | date | str,
    patient_name: str,
    patient_id_card_last4: str,
    companion_id: str,
    template_version: str,
) -> ContractHashResult:
    """Freeze a contract hash + snapshot in one atomic step.

    Caller (ContractService) **must** invoke this once per contract,
    at the moment the contract row is created (payment-succeeded
    handler). The returned ``hash_inputs_snapshot`` dict is written
    verbatim into ``service_contracts.hash_inputs`` JSONB by
    CONTRACT-DOMAIN; the returned ``contract_hash`` populates
    ``service_contracts.contract_hash`` (UNIQUE) and the blob
    filename suffix in ``contract_storage.put_contract``.

    On any field-level validation error, raises
    :class:`ContractHashGenerationError`. CONTRACT-DOMAIN translates
    this into ``status=generation_failed`` (ADR-0046 §3.4 — retry up
    to 3× then permanently_failed + admin alert).

    Args:
        order_id: Order primary key (UUID str).
        amount_cny: Final paid amount in **分** (cents); ``int``. We
            store cents not yuan to make the hash binary-stable even
            when the price column type changes (Decimal → int).
        service_package_id: Service package PK (UUID str).

            ⚠️ Caller note: current ``Order`` model does not carry
            ``service_package_id`` directly; passing
            ``service_name_snapshot`` as a stand-in is **NOT**
            acceptable because the package can be renamed without
            implying contract drift. CONTRACT-DOMAIN should resolve
            the package id from the original cart / payment row before
            calling this fn. This is tracked as a CONTRACT-HASH
            integration note for the architect (S3-DEV-001 review).
        scheduled_at: Service appointment time. Accepts
            ``datetime``/``date``/``str``; normalized to ISO-8601 UTC.
        patient_name: Patient full name.
        patient_id_card_last4: Last 4 chars of patient national ID.
            **Full ID never enters the hash path** (PII minimization).
        companion_id: Accepted companion's user id (UUID str). The
            contract is only generated **after** companion acceptance;
            companion_id is then immutable per ADR-0047.
        template_version: ContractTemplate semver (e.g. ``v1.0.0``).
    """
    pseudonym_hash = compute_patient_pseudonym_hash(
        patient_name=patient_name,
        id_card_last4=patient_id_card_last4,
    )
    snapshot = build_hash_inputs_snapshot(
        order_id=order_id,
        amount_cny=amount_cny,
        service_package_id=service_package_id,
        scheduled_at=scheduled_at,
        patient_pseudonym_hash=pseudonym_hash,
        companion_id=companion_id,
        template_version=template_version,
    )
    contract_hash = _hash_from_snapshot(snapshot, template_version)
    return ContractHashResult(
        contract_hash=contract_hash,
        hash_inputs_snapshot=snapshot,
    )


def recompute_contract_hash(
    *,
    hash_inputs_snapshot: Mapping[str, Any],
    template_version: str,
) -> str:
    """Re-verify a stored contract by recomputing hash from the snapshot.

    Production usage (CONTRACT-DOMAIN audit / dispute resolution):

        snap = db.execute(
            select(service_contracts.hash_inputs).where(...)
        ).scalar_one()
        expected_hash = service_contracts.contract_hash  # stored value
        recomputed = recompute_contract_hash(
            hash_inputs_snapshot=snap,
            template_version=snap['template_version'],
        )
        assert recomputed == expected_hash, "tampered or hash drift"

    Returns the SHA-256 hex string; caller asserts equality with the
    stored ``contract_hash``.
    """
    return _hash_from_snapshot(hash_inputs_snapshot, template_version)


def amount_cny_from_yuan(price_yuan: Decimal | float | int | str) -> int:
    """Convert a yuan price to cents (分) for ``amount_cny``.

    Helper for callers that have a ``Decimal`` from the orders.price
    column. Uses round-half-even at 2 decimals first then ``* 100``
    to dodge binary-float drift. Negative / NaN raise.

    Examples:
        ``Decimal('100.00')`` → ``10000``
        ``Decimal('99.99')``  → ``9999``
        ``Decimal('99.995')`` → ``10000`` (round half even)
    """
    if isinstance(price_yuan, (int, float)):
        price_yuan = Decimal(str(price_yuan))
    elif isinstance(price_yuan, str):
        price_yuan = Decimal(price_yuan)
    if not isinstance(price_yuan, Decimal):
        raise ContractHashGenerationError(
            f"price_yuan must be Decimal/int/float/str, got {type(price_yuan).__name__}"
        )
    if price_yuan.is_nan() or price_yuan < 0:
        raise ContractHashGenerationError(
            f"price_yuan must be non-negative finite, got {price_yuan!r}"
        )
    # Round to 2 decimals (cent precision), then to integer cents.
    cents_decimal = (price_yuan * 100).quantize(Decimal("1"))
    return int(cents_decimal)


__all__ = [
    "ContractHashGenerationError",
    "ContractHashResult",
    "ContractPseudonymSaltMissingError",
    "SHA256_HEX_LEN",
    "amount_cny_from_yuan",
    "build_hash_inputs_snapshot",
    "compute_patient_pseudonym_hash",
    "generate_contract_hash_at_commit_time",
    "recompute_contract_hash",
]
