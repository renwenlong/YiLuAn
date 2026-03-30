import json
from pathlib import Path
from typing import Sequence
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.exceptions import NotFoundException
from app.models.hospital import Hospital
from app.repositories.hospital import HospitalRepository


SEED_FILE = Path(__file__).parent.parent / "data" / "hospitals.json"


class HospitalService:
    def __init__(self, session: AsyncSession):
        self.repo = HospitalRepository(session)

    async def search(
        self,
        *,
        keyword: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Hospital], int]:
        return await self.repo.search(keyword=keyword, skip=skip, limit=limit)

    async def get_by_id(self, hospital_id: UUID) -> Hospital:
        hospital = await self.repo.get_by_id(hospital_id)
        if hospital is None:
            raise NotFoundException("Hospital not found")
        return hospital

    async def seed_hospitals(self) -> int:
        if not SEED_FILE.exists():
            return 0

        with open(SEED_FILE, "r", encoding="utf-8") as f:
            hospitals_data = json.load(f)

        count = 0
        for item in hospitals_data:
            existing, _ = await self.repo.search(keyword=item["name"], skip=0, limit=1)
            if not existing:
                hospital = Hospital(**item)
                await self.repo.create(hospital)
                count += 1

        return count
