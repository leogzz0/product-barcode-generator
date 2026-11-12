import pytest
from pypdf import PdfReader
from reportlab.lib.units import mm

from barcodegen.labels import (
    MIN_MODULE_MM,
    LabelRenderer,
    LabelSize,
    fit_module_width,
    parse_label_size,
)
from barcodegen.products import Product
from barcodegen.symbology import Code128


@pytest.mark.parametrize(
    "text,expected",
    [("50x30", (50, 30)), ("50X30", (50, 30)), (" 62 x 29.5 mm ", (62, 29.5)), ("100×50", (100, 50))],
)
def test_parse_label_size(text, expected):
    size = parse_label_size(text)
    assert (size.width_mm, size.height_mm) == expected


@pytest.mark.parametrize("text", ["50", "50x", "axb", "10x10"])
def test_parse_label_size_rejects_bad_values(text):
    with pytest.raises(ValueError):
        parse_label_size(text)


def test_module_width_snaps_to_printer_dots():
    dot_300 = 25.4 / 300
    module = fit_module_width(145, 50, 300)
    assert module == pytest.approx(3 * dot_300)  # 50 / 165 = 0.303 mm -> 3 dots
    module_203 = fit_module_width(145, 50, 203)
    assert module_203 == pytest.approx(2 * 25.4 / 203)
    assert fit_module_width(145, 50, None) == pytest.approx(50 / 165)


def test_module_width_is_capped_for_short_codes():
    assert fit_module_width(40, 100, None) == pytest.approx(0.40)


def products(*skus, **kw):
    return [Product(line=i + 2, sku=s, name=f"Producto {s}", **kw) for i, s in enumerate(skus)]


def test_one_label_per_page(tmp_path):
    out = tmp_path / "labels.pdf"
    renderer = LabelRenderer(LabelSize(50, 30), Code128())
    renderer.render(products("A-1", "A-2", "A-3"), out)
    reader = PdfReader(out)
    assert len(reader.pages) == 3
    box = reader.pages[0].mediabox
    assert float(box.width) == pytest.approx(50 * mm)
    assert float(box.height) == pytest.approx(30 * mm)
    text = reader.pages[0].extract_text()
    assert "Producto A-1" in text and "A-1" in text
    assert renderer.warnings == []


def test_grid_sheet_packs_labels(tmp_path):
    out = tmp_path / "labels.pdf"
    LabelRenderer(LabelSize(50, 30), Code128(), page="letter").render(
        products(*[f"P-{i}" for i in range(40)]), out
    )
    # Letter with 10 mm margins and 2 mm gaps: 3 columns x 7 rows = 21 per page.
    assert len(PdfReader(out).pages) == 2


def test_lot_and_expiry_are_printed(tmp_path):
    out = tmp_path / "labels.pdf"
    LabelRenderer(LabelSize(60, 30), Code128()).render(
        products("A-1", lot="L261112", expiry="2027-02-12"), out
    )
    text = PdfReader(out).pages[0].extract_text()
    assert "A-1/L261112" in text
    assert "Lote: L261112" in text and "Cad: 2027-02-12" in text


def test_warns_when_code_too_long_for_label(tmp_path):
    renderer = LabelRenderer(LabelSize(50, 30), Code128())
    renderer.render(products("CRM-NVA-ORE-07", lot="L261112"), tmp_path / "labels.pdf")
    assert any(f"< {MIN_MODULE_MM}" in w for w in renderer.warnings)


def test_long_names_are_wrapped_or_truncated(tmp_path):
    out = tmp_path / "labels.pdf"
    long_name = "Helado de yogurt griego con blueberry y granola y muchas cosas más " * 3
    renderer = LabelRenderer(LabelSize(50, 30), Code128())
    renderer.render([Product(2, "A-1", long_name)], out)
    assert "…" in PdfReader(out).pages[0].extract_text()


def test_sample_catalog_fits_50x30_without_warnings(sample_csv, tmp_path):
    from barcodegen.products import load_products

    renderer = LabelRenderer(LabelSize(50, 30), Code128())
    renderer.render(load_products(sample_csv), tmp_path / "labels.pdf")
    assert renderer.warnings == []
