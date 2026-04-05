from typing import Sequence
from uuid import UUID

from sqlalchemy import distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hospital import Hospital
from app.repositories.base import BaseRepository


class HospitalRepository(BaseRepository[Hospital]):
    def __init__(self, session: AsyncSession):
        super().__init__(Hospital, session)

    async def search(
        self,
        *,
        keyword: str | None = None,
        province: str | None = None,
        city: str | None = None,
        district: str | None = None,
        level: str | None = None,
        tag: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[Sequence[Hospital], int]:
        stmt = select(Hospital)
        count_stmt = select(func.count()).select_from(Hospital)

        if keyword:
            stmt = stmt.where(Hospital.name.contains(keyword))
            count_stmt = count_stmt.where(Hospital.name.contains(keyword))
        if province:
            stmt = stmt.where(Hospital.province == province)
            count_stmt = count_stmt.where(Hospital.province == province)
        if city:
            stmt = stmt.where(Hospital.city == city)
            count_stmt = count_stmt.where(Hospital.city == city)
        if district:
            stmt = stmt.where(Hospital.district == district)
            count_stmt = count_stmt.where(Hospital.district == district)
        if level:
            stmt = stmt.where(Hospital.level == level)
            count_stmt = count_stmt.where(Hospital.level == level)
        if tag:
            stmt = stmt.where(Hospital.tags.contains(tag))
            count_stmt = count_stmt.where(Hospital.tags.contains(tag))

        total_result = await self.session.execute(count_stmt)
        total = total_result.scalar_one()

        stmt = stmt.order_by(Hospital.name).offset(skip).limit(limit)
        result = await self.session.execute(stmt)
        return result.scalars().all(), total

    async def get_filter_options(
        self,
        *,
        province: str | None = None,
        city: str | None = None,
    ) -> dict:
        # Provinces
        prov_stmt = select(distinct(Hospital.province)).where(
            Hospital.province.isnot(None)
        ).order_by(Hospital.province)
        prov_result = await self.session.execute(prov_stmt)
        provinces = [r for r in prov_result.scalars().all()]

        # Cities — optionally filtered by province
        city_stmt = select(distinct(Hospital.city)).where(
            Hospital.city.isnot(None)
        )
        if province:
            city_stmt = city_stmt.where(Hospital.province == province)
        city_stmt = city_stmt.order_by(Hospital.city)
        city_result = await self.session.execute(city_stmt)
        cities = [r for r in city_result.scalars().all()]

        # Districts — optionally filtered by city
        dist_stmt = select(distinct(Hospital.district)).where(
            Hospital.district.isnot(None)
        )
        if city:
            dist_stmt = dist_stmt.where(Hospital.city == city)
        elif province:
            dist_stmt = dist_stmt.where(Hospital.province == province)
        dist_stmt = dist_stmt.order_by(Hospital.district)
        dist_result = await self.session.execute(dist_stmt)
        districts = [r for r in dist_result.scalars().all()]

        # Levels
        level_stmt = select(distinct(Hospital.level)).where(
            Hospital.level.isnot(None)
        ).order_by(Hospital.level)
        level_result = await self.session.execute(level_stmt)
        levels = [r for r in level_result.scalars().all()]

        # Tags — flatten comma-separated values
        tag_stmt = select(Hospital.tags).where(Hospital.tags.isnot(None))
        tag_result = await self.session.execute(tag_stmt)
        tag_set: set[str] = set()
        for row in tag_result.scalars().all():
            for t in row.split(","):
                t = t.strip()
                if t:
                    tag_set.add(t)

        return {
            "provinces": provinces,
            "cities": cities,
            "districts": districts,
            "levels": levels,
            "tags": sorted(tag_set),
        }

    async def find_nearest_region(
        self, *, latitude: float, longitude: float
    ) -> dict | None:
        """Find the province/city of the nearest hospital to given coordinates."""
        stmt = select(Hospital).where(
            Hospital.latitude.isnot(None),
            Hospital.longitude.isnot(None),
            Hospital.province.isnot(None),
        ).order_by(
            func.abs(Hospital.latitude - latitude)
            + func.abs(Hospital.longitude - longitude)
        ).limit(1)
        result = await self.session.execute(stmt)
        hospital = result.scalars().first()
        if hospital is None:
            return None
        return {
            "province": hospital.province,
            "city": hospital.city,
        }
