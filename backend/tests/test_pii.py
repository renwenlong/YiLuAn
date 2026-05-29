import pytest

from app.core.pii import mask_id_card, mask_name, mask_phone


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("", ""),
        (None, ""),
        ("1", "*"),
        ("1234", "****"),
        ("12345678", "12****78"),
        ("13812345678", "138******78"),
        ("+8613812345678", "+861********78"),
    ],
)
def test_mask_phone(inp, expected):
    assert mask_phone(inp) == expected


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("", ""),
        (None, ""),
        ("12345678", "********"),
        ("110101199001011234", "1101**********1234"),
    ],
)
def test_mask_id_card(inp, expected):
    assert mask_id_card(inp) == expected


@pytest.mark.parametrize(
    "inp,expected",
    [
        ("", ""),
        (None, ""),
        ("张", "张"),  # 单字无脱敏空间
        ("张三", "张**"),
        ("张小明", "张**"),
        ("Alice", "A**"),
        ("  李四  ", "李**"),  # strip 空白
        ("欧阳娜娜", "欧**"),  # 复姓也只保首字（脱敏强度优先）
    ],
)
def test_mask_name(inp, expected):
    assert mask_name(inp) == expected
