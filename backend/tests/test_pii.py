import pytest

from app.core.pii import mask_id_card, mask_phone


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
