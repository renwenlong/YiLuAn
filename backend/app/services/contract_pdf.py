"""Contract PDF renderer (S3-DEV-001-CONTRACT-PDF-RENDER / uuid 33ac1174).

# Purpose

Pure-function renderer for the v1.0.0 service contract PDF. Called by
:meth:`app.services.contract_service.ContractService._render_pdf` once
``ContractService.generate_now`` (or ``retry_failed``) is ready to
materialize the contract document into WORM blob storage.

# Design (魈 ADR-0046 r5 §3 + PDF-RENDER design gap 拍 (a))

The renderer takes the full :class:`Order` row (already loaded inside
``ContractService``) plus the immutable ``hash_inputs`` snapshot. We
**do not** re-derive any field from the DB inside this module — the
caller is responsible for fetching, this module only formats.

Why a separate module:

* keeps ``contract_service.py`` focused on lifecycle orchestration
* lets the renderer be unit-tested as a pure function (no async,
  no session, no DB)
* future swap to a different PDF library (weasyprint / pdfkit) is
  one module change, not a cross-cut refactor

# Library choice — reportlab

* Pure Python wheel, no system deps (vs weasyprint requiring libpango +
  libcairo C libraries; would inflate the python:3.11-slim Docker layer)
* Built-in ``STSong-Light`` CID font handles Chinese text without
  bundling external TTF files
* ``Canvas(invariant=1)`` guarantees byte-level idempotent output, which
  is critical for AC#5 (hash recompute stability across restarts)

# Idempotency (AC#5)

PDF outputs **must** be byte-level identical for the same input. This
is enforced by:

1. ``Canvas(invariant=1)`` — disables time stamping + sets a
   deterministic file identifier (otherwise reportlab puts a random
   UUID in the ``/ID`` trailer array)
2. No use of ``datetime.now()`` anywhere in the render path; the
   contract "generated at" timestamp is rendered from a fixed sentinel
   that lives in the hash_inputs snapshot
3. Patient name / companion name / etc are read from the Order
   snapshot fields (``patient_name``, ``companion_name``) which are
   frozen at order creation — they cannot drift mid-flight

# Template v1.0.0 (placeholder pending 凝光 文案)

The v1.0.0 template is currently a placeholder layout. When 凝光 lands
the final legal copy (PIPL clauses, service scope, refund terms,
disclaimer boundaries), only :func:`_render_body_paragraphs` needs to
change. The field insertion slots are stable.

# Why don't we ``selectinload(Order.companion, Order.patient)``?

魈's design draft suggested ``selectinload`` to eager-load Companion /
Patient. Investigation showed ``Order`` already carries snapshot
columns (``companion_name``, ``patient_name``, ``hospital_name``,
``service_name_snapshot``, ``service_price_snapshot``) written at
``create_order`` time. These snapshots are the audit-trail source of
truth (contract content must reflect "what the parties agreed to at
booking", not "what the live profile says now"), so no eager-load is
needed. Simpler + safer + matches PII-minimal intent.

If a future template requires data not in the snapshot (e.g. the
companion's current verified id-card last4 for legal binding), add a
dedicated ``ContractService._enrich_for_render(order)`` helper that
returns a typed bundle and keep this module pure.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from io import BytesIO
from typing import Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen.canvas import Canvas

logger = logging.getLogger("app.services.contract_pdf")

# ---------------------------------------------------------------------------
# Font registration (module-level, idempotent)
# ---------------------------------------------------------------------------

_CHINESE_FONT_NAME = "STSong-Light"


def _ensure_chinese_font_registered() -> None:
    """Register the built-in Adobe STSong-Light CID font, once.

    Idempotent: subsequent calls are no-ops (reportlab tolerates
    re-registering the same name).
    """
    if _CHINESE_FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(_CHINESE_FONT_NAME))


_ensure_chinese_font_registered()


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

_PAGE_WIDTH, _PAGE_HEIGHT = A4
_MARGIN_X = 20 * mm
_MARGIN_TOP = 20 * mm
_LINE_HEIGHT = 7 * mm
_TITLE_FONT_SIZE = 16
_HEADING_FONT_SIZE = 12
_BODY_FONT_SIZE = 10
_SMALL_FONT_SIZE = 9


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_contract_pdf(
    *,
    order: Any,
    hash_inputs: dict[str, Any],
    contract_hash: str,
    template_version: str,
) -> bytes:
    """Render the v1.0.0 service contract PDF and return its bytes.

    Args:
        order: :class:`app.models.order.Order` row. Snapshot fields
            (``patient_name``, ``companion_name``, ``hospital_name``,
            ``service_name_snapshot``, ``service_price_snapshot``,
            ``appointment_date``, ``appointment_time``,
            ``family_member_name``, ``family_member_relation``,
            ``order_number``) are the source of truth for rendered
            content. Live profile data is intentionally not consulted.
        hash_inputs: Immutable ``hash_inputs`` JSONB snapshot from
            ``service_contracts.hash_inputs``. Provides
            ``amount_cny``, ``scheduled_at``, ``service_package_id``,
            ``patient_pseudonym_hash``, ``companion_id``,
            ``template_version`` (re-asserted for audit), ``order_id``.
        contract_hash: Hex-encoded SHA-256 of the contract; rendered in
            the footer for human-readable verification.
        template_version: Template version string (e.g. ``"v1.0.0"``).
            Must match ``hash_inputs['template_version']``; mismatch is
            a developer error caught by assert.

    Returns:
        PDF bytes (starts with ``%PDF-`` magic byte). Byte-level
        idempotent: same arguments → same bytes (no timestamp / no
        random UUID in the output).

    Raises:
        ValueError: ``template_version`` mismatches the snapshot
            (means caller wired the wrong template — fail fast).
    """
    snapshot_version = hash_inputs.get("template_version")
    if snapshot_version != template_version:
        raise ValueError(
            f"template_version mismatch: caller={template_version!r} "
            f"snapshot={snapshot_version!r}; refusing to render "
            f"(would produce a contract that fails recompute_contract_hash)"
        )

    buf = BytesIO()
    # invariant=1 → reportlab disables timestamps and sets a deterministic
    # file identifier. WITHOUT this flag, the /ID array in the PDF trailer
    # contains a random UUID and /CreationDate / /ModDate are set to wall
    # clock — both break AC#5 byte-level idempotency.
    canvas = Canvas(buf, pagesize=A4, invariant=1)
    canvas.setTitle(f"陪诊服务合同 {order.order_number}")
    canvas.setAuthor("一路安")
    canvas.setSubject(f"合同版本 {template_version}")

    cursor_y = _PAGE_HEIGHT - _MARGIN_TOP
    cursor_y = _draw_title(canvas, cursor_y)
    cursor_y = _draw_parties_section(canvas, cursor_y, order=order)
    cursor_y = _draw_service_section(canvas, cursor_y, order=order, hash_inputs=hash_inputs)
    cursor_y = _draw_body_paragraphs(canvas, cursor_y)
    _draw_footer(
        canvas,
        order=order,
        hash_inputs=hash_inputs,
        contract_hash=contract_hash,
        template_version=template_version,
    )

    canvas.showPage()
    canvas.save()
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------


def _draw_title(canvas: Canvas, cursor_y: float) -> float:
    canvas.setFont(_CHINESE_FONT_NAME, _TITLE_FONT_SIZE)
    canvas.drawCentredString(_PAGE_WIDTH / 2, cursor_y, "陪诊服务合同")
    return cursor_y - _LINE_HEIGHT * 2


def _draw_parties_section(canvas: Canvas, cursor_y: float, *, order: Any) -> float:
    canvas.setFont(_CHINESE_FONT_NAME, _HEADING_FONT_SIZE)
    canvas.drawString(_MARGIN_X, cursor_y, "一、合同当事人")
    cursor_y -= _LINE_HEIGHT

    canvas.setFont(_CHINESE_FONT_NAME, _BODY_FONT_SIZE)
    patient_display = _format_patient_display(order)
    canvas.drawString(
        _MARGIN_X + 5 * mm,
        cursor_y,
        f"用户(甲方):{patient_display}",
    )
    cursor_y -= _LINE_HEIGHT
    companion_name = order.companion_name or "(待陪诊师接单)"
    canvas.drawString(
        _MARGIN_X + 5 * mm,
        cursor_y,
        f"陪诊师(乙方):{companion_name}",
    )
    cursor_y -= _LINE_HEIGHT
    canvas.drawString(
        _MARGIN_X + 5 * mm,
        cursor_y,
        "平台(居间方):一路安",
    )
    return cursor_y - _LINE_HEIGHT


def _draw_service_section(
    canvas: Canvas,
    cursor_y: float,
    *,
    order: Any,
    hash_inputs: dict[str, Any],
) -> float:
    canvas.setFont(_CHINESE_FONT_NAME, _HEADING_FONT_SIZE)
    canvas.drawString(_MARGIN_X, cursor_y, "二、服务内容")
    cursor_y -= _LINE_HEIGHT

    canvas.setFont(_CHINESE_FONT_NAME, _BODY_FONT_SIZE)
    service_name = order.service_name_snapshot or "陪诊服务"
    canvas.drawString(_MARGIN_X + 5 * mm, cursor_y, f"服务项目:{service_name}")
    cursor_y -= _LINE_HEIGHT

    hospital = order.hospital_name or "(未指定)"
    canvas.drawString(_MARGIN_X + 5 * mm, cursor_y, f"服务地点:{hospital}")
    cursor_y -= _LINE_HEIGHT

    scheduled_display = _format_scheduled(order)
    canvas.drawString(_MARGIN_X + 5 * mm, cursor_y, f"预约时间:{scheduled_display}")
    cursor_y -= _LINE_HEIGHT

    amount_yuan = _format_amount_cny_as_yuan(hash_inputs.get("amount_cny"))
    canvas.drawString(_MARGIN_X + 5 * mm, cursor_y, f"服务费用:人民币 {amount_yuan} 元")
    return cursor_y - _LINE_HEIGHT * 2


def _draw_body_paragraphs(canvas: Canvas, cursor_y: float) -> float:
    """Render the legal body paragraphs.

    v1.0.0 placeholder pending 凝光 final legal copy. Layout slots:

    - 服务范围 / Service scope
    - 退款规则 / Refund rules
    - 免责边界 / Disclaimer boundaries
    - PIPL 个人信息处理说明 / PIPL data handling notice

    When 凝光 lands the final copy, replace ``_PLACEHOLDER_PARAGRAPHS``
    with the approved text. Renderer logic does not need to change.
    """
    canvas.setFont(_CHINESE_FONT_NAME, _HEADING_FONT_SIZE)
    canvas.drawString(_MARGIN_X, cursor_y, "三、合同条款")
    cursor_y -= _LINE_HEIGHT

    canvas.setFont(_CHINESE_FONT_NAME, _BODY_FONT_SIZE)
    for heading, paragraph in _PLACEHOLDER_PARAGRAPHS:
        canvas.setFont(_CHINESE_FONT_NAME, _BODY_FONT_SIZE)
        canvas.drawString(_MARGIN_X + 5 * mm, cursor_y, heading)
        cursor_y -= _LINE_HEIGHT
        canvas.setFont(_CHINESE_FONT_NAME, _SMALL_FONT_SIZE)
        # Simple wrap: split by line break in the placeholder; production
        # copy from 凝光 may need ``Platypus.Paragraph`` for full justification.
        for line in paragraph.split("\n"):
            canvas.drawString(_MARGIN_X + 8 * mm, cursor_y, line)
            cursor_y -= _LINE_HEIGHT * 0.8
        cursor_y -= _LINE_HEIGHT * 0.5
    return cursor_y


def _draw_footer(
    canvas: Canvas,
    *,
    order: Any,
    hash_inputs: dict[str, Any],
    contract_hash: str,
    template_version: str,
) -> None:
    """Render audit metadata (order id, contract hash, template version).

    Lives at the bottom of the page so the user can quote it back when
    asking the platform to verify authenticity of a specific contract.
    """
    canvas.setFont(_CHINESE_FONT_NAME, _SMALL_FONT_SIZE)
    footer_y = 20 * mm
    canvas.drawString(_MARGIN_X, footer_y, f"订单号:{order.order_number}")
    canvas.drawString(_MARGIN_X, footer_y - _LINE_HEIGHT * 0.7, f"模板版本:{template_version}")
    canvas.drawString(
        _MARGIN_X,
        footer_y - _LINE_HEIGHT * 1.4,
        f"合同哈希:{contract_hash}",
    )
    scheduled_iso = hash_inputs.get("scheduled_at", "")
    canvas.drawString(
        _MARGIN_X,
        footer_y - _LINE_HEIGHT * 2.1,
        f"快照时间:{scheduled_iso}",
    )


# ---------------------------------------------------------------------------
# Field formatting
# ---------------------------------------------------------------------------


def _format_patient_display(order: Any) -> str:
    """Render the patient display name.

    Handles the 代他人下单 (book on behalf) case: when
    ``family_member_name`` is present, the contract is for that family
    member, with the booking patient as the contact. Otherwise the
    patient books for themselves.
    """
    patient_name = (order.patient_name or "").strip()
    family_name = (order.family_member_name or "").strip()
    family_relation = (order.family_member_relation or "").strip()
    if family_name:
        if family_relation:
            return f"{family_name}({family_relation},由 {patient_name or '本人'} 代订)"
        return f"{family_name}(由 {patient_name or '本人'} 代订)"
    return patient_name or "(未填写)"


def _format_scheduled(order: Any) -> str:
    appointment_date = order.appointment_date or ""
    appointment_time = order.appointment_time or ""
    if appointment_date and appointment_time:
        return f"{appointment_date} {appointment_time}"
    return appointment_date or appointment_time or "(未设定)"


def _format_amount_cny_as_yuan(amount_cny: int | None) -> str:
    """Format integer fen → yuan with 2-decimal display."""
    if amount_cny is None:
        return "0.00"
    # Use Decimal to avoid float drift on the display string.
    yuan = Decimal(amount_cny) / Decimal(100)
    return f"{yuan:.2f}"


# ---------------------------------------------------------------------------
# Placeholder legal copy (pending 凝光 final v1.0.0 文案)
# ---------------------------------------------------------------------------

# Legal copy v1.0.0-draft (PM 凝光 2026-06-08 10:18 UTC 交付)
# Source: docs/qa/s3-contract-template-v1.0.0-paragraphs.md
# 全文字面对齐凝光交付。仅一点调整: 凝光原文 `30%%/50%%` (预防
# Python format-string 处理)改为单个 `%` — 本渲染走 `canvas.drawString`
# 直接字面输出, 不走 % format, 单个 `%` 不会被 escape 。
#
# 调设点: 凝光原文 "补偿(由客服评估)" / "客服" 里提及的客服电话占位
# 仍未填 (等帝君拍主体电话后凝光走小 PR amend); 字面 “客服” 仍是
# 全可读。
# 锁版条件 (v1.0.0-draft → v1.0.0): 帝君 PRD-003 v0.5 Owner Accept + 主体/
# 客服/司法管辖地 3 处补齐 + (可选) 法务 review 。
_PLACEHOLDER_PARAGRAPHS: list[tuple[str, str]] = [
    (
        "1. 服务范围",
        "乙方按订单服务项目向甲方提供陪诊相关服务,包括就诊陪同、挂号取号、缴费取药、\n"
        "导诊协助、医嘱要点记录、就诊流程沟通协助。乙方明确不提供以下内容:\n"
        "(a) 任何医疗诊断、用药建议、剂量建议、治疗方案建议;\n"
        "(b) 报告解读结论性表达(如'是什么病'、'建议手术');\n"
        "(c) 代签任何医疗同意书或代为决策医疗方案;\n"
        "(d) 超出陪诊范围的护理操作(喂药/注射/伤口处理/生命体征监测等)。\n"
        "如甲方要求超出上述范围的服务,乙方应明确拒绝并提醒甲方联系医生。",
    ),
    (
        "2. 退款规则",
        "服务开始前 24 小时以上取消:全额退款。\n"
        "服务开始前 24 小时内、12 小时以上取消:扣 30% 服务费,余额退款。\n"
        "服务开始前 12 小时内取消:扣 50% 服务费,余额退款。\n"
        "服务开始后取消:按实际完成比例结算,最少结算 50%。\n"
        "因平台或乙方原因取消:全额退款 + 平台补偿(由客服评估)。\n"
        "退款通过订单详情页'申请退款'按钮发起,平台 24 小时内审核,\n"
        "退款到账 1-7 个工作日按原渠道返回。",
    ),
    (
        "3. 免责边界",
        "乙方不构成医疗服务提供者,平台不对甲方任何医疗结果承担责任。\n"
        "乙方仅按订单约定提供陪诊协助,医疗决策与医嘱执行由甲方自行负责。\n"
        "因不可抗力(自然灾害、政府行为、医院系统故障等)导致服务无法履行的,\n"
        "双方均不承担违约责任。\n"
        "因甲方提供的信息不实导致服务无法履行的,乙方与平台不承担退款责任。\n"
        "平台不就乙方在医疗机构的任何在册职业身份做任何形式背书或宣传,\n"
        "乙方在本次服务中身份仅为'平台陪诊师'。",
    ),
    (
        "4. 个人信息处理(PIPL)",
        "平台依据《个人信息保护法》第十三条第(二)项'为订立、履行个人作为\n"
        "一方当事人的合同所必需'处理甲乙双方个人信息。\n"
        "处理范围:姓名、电话、就诊信息(医院/科室/时间)、支付订单信息。\n"
        "保留期限:合同履行完毕后保留 3 年(满足《电子商务法》合规要求),\n"
        "期满后去标识化处理。\n"
        "合同哈希采用 SHA-256 算法,患者姓名、身份证后四位以伪名化(salted\n"
        "SHA-256)形式参与哈希计算,本合同 PDF 不存储任何敏感明文。\n"
        "甲方有权通过平台客服查阅、复制、更正本人个人信息,或撤回同意。\n"
        "详细 PIPL 条款见《一路安隐私政策》。",
    ),
]


__all__ = ["render_contract_pdf"]
