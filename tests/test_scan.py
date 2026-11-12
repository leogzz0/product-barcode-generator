"""Round-trip check: decode the generated images with a real barcode reader.

Skipped unless the optional decoders are installed:
    pip install zxing-cpp pypdfium2
"""

import csv

import pytest

zxingcpp = pytest.importorskip("zxingcpp")
pdfium = pytest.importorskip("pypdfium2")

from PIL import Image  # noqa: E402

from barcodegen.cli import main  # noqa: E402


def test_every_png_and_label_decodes(sample_csv, tmp_path):
    out = tmp_path / "output"
    assert main(["generate", str(sample_csv), "-o", str(out)]) == 0
    rows = list(csv.DictReader((out / "manifest.csv").open(encoding="utf-8")))

    for row in rows:
        found = [r.text for r in zxingcpp.read_barcodes(Image.open(out / row["png_file"]))]
        assert found == [row["encoded_value"]], row["sku"]

    pdf = pdfium.PdfDocument(out / "labels.pdf")
    for row, page in zip(rows, pdf, strict=True):
        image = page.render(scale=300 / 72).to_pil()  # like a 300 dpi label printer
        found = [r.text for r in zxingcpp.read_barcodes(image)]
        assert found == [row["encoded_value"]], row["sku"]
