import pytest

from barcodegen.products import Product
from barcodegen.symbology import Code128, Ean13, ean13_check_digit, get_symbology


def product(**kw):
    return Product(line=2, **{"sku": "NVA-ORE-07", "name": "Nieve", **kw})


def test_code128_encodes_sku():
    assert Code128().encode(product()) == "NVA-ORE-07"


def test_code128_appends_lot():
    assert Code128().encode(product(lot="L261112")) == "NVA-ORE-07/L261112"
    assert Code128(lot_separator="+").encode(product(lot="L1")) == "NVA-ORE-07+L1"


def test_code128_rejects_separator_inside_values():
    assert Code128(lot_separator="-").check(product(lot="L1"))
    assert Code128().check(product(lot="L1")) == []


def test_code128_modules_are_bars_and_spaces():
    modules = Code128().modules("NVA-ORE-07")
    assert set(modules) == {"0", "1"}
    assert len(modules) == 11 * (10 + 2) + 13  # start + 10 chars + check, then stop


@pytest.mark.parametrize(
    "gtin",
    ["4006381333931", "5901234123457", "7501055300846", "0012345678905"],
)
def test_ean13_check_digit_known_codes(gtin):
    assert ean13_check_digit(gtin[:12]) == gtin[12]


def test_ean13_check_digit_rejects_bad_input():
    with pytest.raises(ValueError):
        ean13_check_digit("12345")


def test_ean13_builds_gtin_from_prefix_and_item_ref():
    sym = Ean13("7501234")
    value = sym.encode(product(item_ref="17"))
    assert value == "750123400017" + ean13_check_digit("750123400017")
    assert sym.make(value).get_fullcode() == value  # python-barcode agrees


def test_ean13_requires_prefix_and_item_ref():
    with pytest.raises(ValueError):
        Ean13(None)
    with pytest.raises(ValueError):
        Ean13("75A")
    sym = Ean13("7501234")
    assert sym.check(product())  # no item_ref
    assert sym.check(product(item_ref="123456"))  # too long for a 7-digit prefix
    assert sym.check(product(item_ref="12345")) == []
    assert sym.notes(product(item_ref="1", lot="L1"))  # lot cannot be encoded


def test_get_symbology():
    assert isinstance(get_symbology("code128"), Code128)
    assert isinstance(get_symbology("ean13", gs1_prefix="7501234"), Ean13)
    with pytest.raises(ValueError, match="unknown symbology"):
        get_symbology("qr")
