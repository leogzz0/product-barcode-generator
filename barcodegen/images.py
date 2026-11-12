"""Standalone PNG and SVG barcode files."""

from __future__ import annotations

from pathlib import Path

from barcode.writer import ImageWriter, SVGWriter

from barcodegen.symbology import Symbology

NOMINAL_MODULE_MM = 0.254  # 10 mil, a common "comfortable" bar width
QUIET_ZONE_MODULES = 15  # spec minimum is 10; extra margin helps on curved cups
BAR_HEIGHT_MM = 15.0


def module_width_mm(dpi: int) -> float:
    """Nominal module width rounded to a whole number of pixels at ``dpi``.

    Whole pixels keep every bar the same width; fractional widths make some bars
    one pixel wider than others, which hurts scanning.
    """
    px = max(1, round(NOMINAL_MODULE_MM * dpi / 25.4))
    return px * 25.4 / dpi


def writer_options(dpi: int) -> dict:
    module = module_width_mm(dpi)
    return {
        "module_width": module,
        "module_height": BAR_HEIGHT_MM,
        "quiet_zone": QUIET_ZONE_MODULES * module,
        "font_size": 10,
        "text_distance": 4,
        "dpi": dpi,
    }


def write_images(symbology: Symbology, value: str, png_path: Path, svg_path: Path, dpi: int) -> None:
    if dpi < 300:
        raise ValueError("dpi must be at least 300")
    options = writer_options(dpi)
    # render() returns the PIL image; save it ourselves so the file carries its DPI
    # (python-barcode does not), and prints at the intended physical size.
    image = symbology.make(value, writer=ImageWriter(format="PNG", dpi=dpi)).render(options)
    image.save(png_path, format="PNG", dpi=(dpi, dpi))
    with svg_path.open("wb") as fh:
        symbology.make(value, writer=SVGWriter()).write(fh, options)
