"""End-to-end pipeline: products -> barcode files, label PDF, manifest."""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path

from barcodegen.images import write_images
from barcodegen.labels import LabelRenderer, LabelSize
from barcodegen.products import InputError, Product
from barcodegen.symbology import Symbology

MANIFEST_COLUMNS = ["sku", "name", "lot", "symbology", "encoded_value", "png_file", "svg_file"]


@dataclass
class Result:
    count: int
    barcodes_dir: Path
    labels_pdf: Path
    manifest: Path
    warnings: list[str] = field(default_factory=list)


def check_products(products: list[Product], symbology: Symbology) -> list[str]:
    """Symbology-specific validation. Raises InputError; returns warnings."""
    errors = [e for p in products for e in symbology.check(p)]
    if errors:
        raise InputError(errors)
    return [n for p in products for n in symbology.notes(p)]


def generate(
    products: list[Product],
    symbology: Symbology,
    output_dir: Path,
    label_size: LabelSize,
    page: str = "label",
    printer_dpi: int | None = 300,
    image_dpi: int = 600,
) -> Result:
    warnings = check_products(products, symbology)

    barcodes_dir = output_dir / "barcodes"
    barcodes_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for p in products:
        value = symbology.encode(p)
        png, svg = barcodes_dir / f"{p.sku}.png", barcodes_dir / f"{p.sku}.svg"
        write_images(symbology, value, png, svg, dpi=image_dpi)
        rows.append(
            {
                "sku": p.sku,
                "name": p.name,
                "lot": p.lot,
                "symbology": symbology.name,
                "encoded_value": value,
                "png_file": png.relative_to(output_dir).as_posix(),
                "svg_file": svg.relative_to(output_dir).as_posix(),
            }
        )

    labels_pdf = output_dir / "labels.pdf"
    renderer = LabelRenderer(label_size, symbology, page=page, printer_dpi=printer_dpi)
    renderer.render(products, labels_pdf)
    warnings += renderer.warnings

    manifest = output_dir / "manifest.csv"
    with manifest.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=MANIFEST_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return Result(len(products), barcodes_dir, labels_pdf, manifest, warnings)
