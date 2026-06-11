"""Recommendation service — wires DB + ranking algorithm + response shaping.

Spec source: ``docs/prd/drafts/2026-06-11-s3-prd-001-f8-recommendation-filter-spec-v1-final.md``
§2.1 endpoint URL + §2.2 response shape + §1.4 admin override 守门.

ABAC defense layers (ADR-0049 §6, 4-layer):
  - Layer 1: Depends(get_current_user) at endpoint (any authenticated user)
  - Layer 2: This service — SELECT all profiles (cert ranking needs all 3 states),
            then map to RankingCandidate (PII-free dataclass), sort, filter top3.
            ``_to_recommendation_item`` projects to RecommendationItem dict.
  - Layer 3: ``RecommendationItem`` schema — positive list, 0 PII fields
  - Layer 4: ``test_recommendation_response_field_set_locked`` sentinel test

PR #282 ABAC fix (CompanionDirectoryView for /v1/companions list+detail)
is independent — this service does NOT reuse CompanionDirectoryView because
recommendation needs extra ranking metadata (recommended / recommendation_rank)
and uses spec-literal field names (rating / completed_orders / companion_cert_status)
via service mapping, not model字面 (avg_rating / total_orders / verification_status).

魈拍板方案 B (2026-06-11): 0 DB migration. Service-layer facade mapping
via ``map_verification_to_cert_status`` (in services/recommendation.py).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pii import mask_name
from app.repositories.companion_profile import CompanionProfileRepository
from app.schemas.recommendation import (
    CompanionCertStatus,
    RecommendationItem,
    RecommendationResponse,
)
from app.services.recommendation import (
    companion_to_ranking_candidate,
    filter_top3_recommendations,
    map_verification_to_cert_status,
    sort_companions_for_recommendation,
)

if TYPE_CHECKING:
    from app.models.companion_profile import CompanionProfile


def _to_recommendation_item(
    profile: "CompanionProfile",
    *,
    recommended: bool,
    rank: int | None,
) -> dict:
    """Project ``CompanionProfile`` model row → ``RecommendationItem`` dict.

    Reuses ``app.core.pii.mask_name`` for ``pseudonym_name`` (反案 #14 SSoT,
    same as ``CompanionDirectoryView._to_public_view`` in companion_profile service).

    Args:
        profile: model row (PII fields ignored here, never returned).
        recommended: spec §1.2 推荐位标识 (computed by ``filter_top3_recommendations``).
        rank: spec §1.2 推荐位排名 (1-3 if recommended, None otherwise).

    Returns:
        dict shaped for ``RecommendationItem`` model_validate.
    """
    return {
        "companion_id": profile.id,
        "pseudonym_name": mask_name(profile.real_name) if profile.real_name else None,
        "bio": profile.bio,
        "service_city": profile.service_city,
        "service_area": profile.service_area,
        "service_types": profile.service_types,
        "companion_cert_status": map_verification_to_cert_status(
            profile.verification_status, companion_id=str(profile.id)
        ),
        "avg_rating": profile.avg_rating,  # Pydantic validation_alias → rating
        "total_orders": profile.total_orders,  # validation_alias → completed_orders
        "recommended": recommended,
        "recommendation_rank": rank,
        "created_at": profile.created_at,
    }


class RecommendationService:
    """Wire repo + ranking algorithm + response for ``GET /v1/companions/recommendations``."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.repo = CompanionProfileRepository(session)

    async def get_top_recommendations(
        self,
        *,
        city: str | None = None,
        top_k: int = 3,
    ) -> RecommendationResponse:
        """Return spec §2.2 response shape.

        Steps:
          1. SELECT all profiles (optionally city-filtered)
          2. Project to RankingCandidate (PII-free, spec字面)
          3. Sort by spec §1.3 (cert_status > rating > completed_orders > created_at)
          4. Filter top_k (drops uncertified per §1.4 守门)
          5. Project original CompanionProfile rows back to RecommendationItem
             with recommendation_rank assigned (top3 = 1-3, others = None)

        Args:
            city: optional city filter (spec §1.5)
            top_k: top N recommendations (spec §2.1 default=3, max=3)

        Returns:
            RecommendationResponse with items (max top_k) + meta counts.
        """
        # 1+2: load + project
        profiles = await self.repo.list_for_recommendations(city=city)
        candidates = [companion_to_ranking_candidate(p) for p in profiles]
        # Build candidate_id → profile lookup for step 5 projection.
        profile_by_id = {str(p.id): p for p in profiles}

        # 3: sort
        sorted_candidates = sort_companions_for_recommendation(candidates)

        # 4: filter top_k (drops uncertified per §1.4)
        top_recommendations = filter_top3_recommendations(sorted_candidates, limit=top_k)

        # 5: project model rows back to RecommendationItem (with rank assigned)
        items: list[RecommendationItem] = []
        for rank_index, candidate in enumerate(top_recommendations, start=1):
            profile = profile_by_id[candidate.companion_id]
            item_dict = _to_recommendation_item(
                profile, recommended=True, rank=rank_index
            )
            items.append(RecommendationItem.model_validate(item_dict))

        # Meta counts (spec §2.2 transparency)
        eligible_count = sum(
            1
            for c in candidates
            if c.companion_cert_status != CompanionCertStatus.uncertified
        )
        uncertified_count = sum(
            1
            for c in candidates
            if c.companion_cert_status == CompanionCertStatus.uncertified
        )

        return RecommendationResponse(
            items=items,
            total_eligible=eligible_count,
            filtered_uncertified_count=uncertified_count,
        )
