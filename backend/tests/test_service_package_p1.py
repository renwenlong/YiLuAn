"""S2-REQ-003-P1: service_packages model 单测

注意：alembic seed (bulk_insert 3 行) 在测试环境**不跑** (conftest 用 Base.metadata.create_all
绕过 migration), 所以测试需要手动 insert seed 行验证 model 行为.

alembic migration + seed 的 staging 真行为由 deploy/staging/up.sh 跑 alembic upgrade head 验证.

acceptance:
- model 字段 (code/name/price/is_active/sort_order/audit) 正确
- Decimal 精度保留 (ADR-0030)
- code 全局唯一约束
- repr 包含关键字段
"""
import pytest
import uuid
from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.models.service_package import ServicePackage
from tests.conftest import test_session_factory


async def _seed_one(code: str, name: str, price: Decimal, sort_order: int = 0, **kwargs) -> uuid.UUID:
    """测试 helper: 手动 insert 1 行 service_package (因 conftest 不跑 alembic seed)."""
    pkg_id = uuid.uuid4()
    async with test_session_factory() as session:
        pkg = ServicePackage(
            id=pkg_id,
            code=code,
            name=name,
            price=price,
            is_active=kwargs.get("is_active", True),
            sort_order=sort_order,
            description=kwargs.get("description"),
        )
        session.add(pkg)
        await session.commit()
    return pkg_id


@pytest.mark.asyncio
async def test_servicepackage_model_basic_crud():
    """基础 CRUD: insert + select 后字段一致."""
    pkg_id = await _seed_one("full_accompany", "全程陪诊", Decimal("299.00"), 10)

    async with test_session_factory() as session:
        pkg = await session.get(ServicePackage, pkg_id)

    assert pkg is not None
    assert pkg.code == "full_accompany"
    assert pkg.name == "全程陪诊"
    assert pkg.price == Decimal("299.00")
    assert isinstance(pkg.price, Decimal)
    assert pkg.is_active is True
    assert pkg.sort_order == 10
    assert pkg.created_at is not None
    assert pkg.updated_at is not None


@pytest.mark.asyncio
async def test_servicepackage_decimal_precision():
    """ADR-0030: 价格用 Decimal('299.00') 不是 float."""
    await _seed_one("test_decimal", "测试", Decimal("199.99"), 1)

    async with test_session_factory() as session:
        pkg = (await session.execute(
            select(ServicePackage).where(ServicePackage.code == "test_decimal")
        )).scalar_one()

    # Numeric(10,2) round-trip 保 2 位精度
    assert pkg.price == Decimal("199.99")
    # 不应被转 float
    assert not isinstance(pkg.price, float)


@pytest.mark.asyncio
async def test_servicepackage_code_uniqueness():
    """code 全局唯一约束: 重复 insert 报 IntegrityError."""
    await _seed_one("unique_test", "唯一", Decimal("100.00"), 1)

    async with test_session_factory() as session:
        dup = ServicePackage(
            id=uuid.uuid4(),
            code="unique_test",  # 重复
            name="重复",
            price=Decimal("200.00"),
            is_active=True,
            sort_order=2,
        )
        session.add(dup)
        with pytest.raises(IntegrityError):
            await session.commit()
        await session.rollback()


@pytest.mark.asyncio
async def test_servicepackage_default_values():
    """默认值: is_active=True / sort_order=0 / created_at + updated_at 自动."""
    pkg_id = uuid.uuid4()
    async with test_session_factory() as session:
        pkg = ServicePackage(
            id=pkg_id,
            code="defaults_test",
            name="默认测试",
            price=Decimal("50.00"),
            # is_active / sort_order / created_at / updated_at 走默认
        )
        session.add(pkg)
        await session.commit()
        await session.refresh(pkg)

    assert pkg.is_active is True
    assert pkg.sort_order == 0
    assert pkg.created_at is not None
    assert pkg.updated_at is not None
    assert pkg.description is None
    assert pkg.created_by is None
    assert pkg.updated_by is None


@pytest.mark.asyncio
async def test_servicepackage_sort_order_query():
    """sort_order 升序排正确."""
    await _seed_one("first", "第一档", Decimal("100"), 10)
    await _seed_one("second", "第二档", Decimal("200"), 20)
    await _seed_one("third", "第三档", Decimal("300"), 30)

    async with test_session_factory() as session:
        rows = (await session.execute(
            select(ServicePackage)
            .where(ServicePackage.code.in_(["first", "second", "third"]))
            .order_by(ServicePackage.sort_order)
        )).scalars().all()

    assert [r.code for r in rows] == ["first", "second", "third"]
    assert [r.sort_order for r in rows] == [10, 20, 30]


@pytest.mark.asyncio
async def test_servicepackage_is_active_filter():
    """is_active 过滤 (软删场景)."""
    await _seed_one("active_test", "启用中", Decimal("100"), 1, is_active=True)
    await _seed_one("inactive_test", "已停用", Decimal("100"), 2, is_active=False)

    async with test_session_factory() as session:
        active_rows = (await session.execute(
            select(ServicePackage).where(
                ServicePackage.code.in_(["active_test", "inactive_test"]),
                ServicePackage.is_active.is_(True),
            )
        )).scalars().all()

    assert len(active_rows) == 1
    assert active_rows[0].code == "active_test"


@pytest.mark.asyncio
async def test_servicepackage_repr():
    """__repr__ 包含关键字段."""
    sp = ServicePackage(
        id=uuid.uuid4(),
        code="repr_test",
        name="测试 repr",
        price=Decimal("100.00"),
        is_active=True,
        sort_order=99,
    )
    r = repr(sp)
    assert "repr_test" in r
    assert "测试 repr" in r
    assert "100" in r
    assert "is_active=True" in r
    assert "sort_order=99" in r


@pytest.mark.asyncio
async def test_servicepackage_long_chinese_name():
    """name 支持长中文名 (String(100))."""
    long_name = "全程陪诊（含上海三甲医院专家挂号）"
    pkg_id = await _seed_one("long_name", long_name, Decimal("999.00"), 1)

    async with test_session_factory() as session:
        pkg = await session.get(ServicePackage, pkg_id)

    assert pkg.name == long_name
