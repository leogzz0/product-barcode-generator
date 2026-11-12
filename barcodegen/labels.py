"""Printable label PDF (vector bars, sized for thermal label printers or sheets)."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from barcodegen.products import Product
from barcodegen.symbology import Symbology

PAGE_SIZES = {"a4": A4, "letter": LETTER}

MIN_MODULE_MM = 0.19  # below ~7.5 mil most handheld scanners struggle
MAX_MODULE_MM = 0.40  # no benefit from fatter bars on a small label
QUIET_ZONE_MODULES = 10  # Code 128 / EAN minimum on each side
PADDING_MM = 1.5
MIN_BAR_HEIGHT_MM = 8.0

NAME_FONT, NAME_MAX_PT, NAME_MIN_PT = "Helvetica-Bold", 8.0, 5.5
CODE_FONT, CODE_PT = "Helvetica", 7.0
INFO_FONT, INFO_PT = "Helvetica", 6.0


@dataclass(frozen=True)
class LabelSize:
    width_mm: float
    height_mm: float

    def __str__(self) -> str:
        return f"{self.width_mm:g}x{self.height_mm:g} mm"


def parse_label_size(text: str) -> LabelSize:
    """Parse '50x30' (millimetres) into a LabelSize."""
    m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)\s*(?:mm)?\s*", text)
    if not m:
        raise ValueError(f"invalid label size {text!r}; use WIDTHxHEIGHT in mm, e.g. 50x30")
    w, h = float(m.group(1)), float(m.group(2))
    if w < 20 or h < 15:
        raise ValueError(f"label size {text!r} is too small (minimum 20x15 mm)")
    return LabelSize(w, h)


def fit_module_width(n_modules: int, available_mm: float, printer_dpi: int | None) -> float:
    """Widest module (bar unit) so bars + quiet zones fit, snapped to printer dots."""
    module = min(available_mm / (n_modules + 2 * QUIET_ZONE_MODULES), MAX_MODULE_MM)
    if printer_dpi:
        dot = 25.4 / printer_dpi
        module = math.floor(module / dot + 1e-9) * dot
    return module


def _wrap(text: str, font: str, size: float, width: float, max_lines: int) -> list[str] | None:
    words, lines, current = text.split(), [], ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if stringWidth(candidate, font, size) <= width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
            if stringWidth(word, font, size) > width:
                return None
    if current:
        lines.append(current)
    return lines if len(lines) <= max_lines else None


def _fit_name(name: str, width: float) -> tuple[list[str], float]:
    size = NAME_MAX_PT
    while size >= NAME_MIN_PT:
        lines = _wrap(name, NAME_FONT, size, width, max_lines=2)
        if lines:
            return lines, size
        size -= 0.5
    # Last resort: truncate at the smallest size.
    text = name
    while text and stringWidth(text + "…", NAME_FONT, NAME_MIN_PT) > width:
        text = text[:-1]
    return [text.rstrip() + "…"], NAME_MIN_PT


@dataclass
class _Label:
    product: Product
    value: str
    modules: str


class LabelRenderer:
    def __init__(
        self,
        size: LabelSize,
        symbology: Symbology,
        page: str = "label",
        printer_dpi: int | None = 300,
    ):
        if page != "label" and page not in PAGE_SIZES:
            raise ValueError(f"unknown page {page!r} (choose label, {', '.join(PAGE_SIZES)})")
        self.size = size
        self.symbology = symbology
        self.page = page
        self.printer_dpi = printer_dpi
        self.warnings: list[str] = []

    # -- layout of a single label, origin at its bottom-left corner -------------
    def _draw_label(self, c: Canvas, x0: float, y0: float, label: _Label) -> None:
        w, h = self.size.width_mm * mm, self.size.height_mm * mm
        pad = PADDING_MM * mm
        inner_w = w - 2 * pad
        product = label.product

        # Top: product name (1-2 lines, shrinks to fit).
        lines, name_pt = _fit_name(product.name, inner_w)
        y = y0 + h - pad
        c.setFont(NAME_FONT, name_pt)
        for line in lines:
            y -= name_pt
            c.drawCentredString(x0 + w / 2, y, line)
            y -= name_pt * 0.15
        bars_top = y - 0.8 * mm

        # Bottom: lot / expiry line (only when present).
        bottom = y0 + pad
        info = []
        if product.lot:
            info.append(f"Lote: {product.lot}")
        if product.expiry:
            info.append(f"Cad: {product.expiry}")
        if info:
            c.setFont(INFO_FONT, INFO_PT)
            c.drawCentredString(x0 + w / 2, bottom + 0.25 * INFO_PT, "   ".join(info))
            bottom += INFO_PT + 0.6 * mm

        # Human-readable encoded value directly under the bars.
        c.setFont(CODE_FONT, CODE_PT)
        c.drawCentredString(x0 + w / 2, bottom + 0.2 * CODE_PT, label.value)
        bars_bottom = bottom + CODE_PT + 0.6 * mm

        bar_h = bars_top - bars_bottom
        if bar_h < MIN_BAR_HEIGHT_MM * mm:
            self.warnings.append(
                f"{product.sku}: bars are only {bar_h / mm:.1f} mm tall on a {self.size} label "
                f"(recommended >= {MIN_BAR_HEIGHT_MM:g} mm); use a taller label or a shorter name"
            )

        # Bars: quiet zones may use the label padding, so fit against the full width.
        n = len(label.modules)
        module = fit_module_width(n, self.size.width_mm, self.printer_dpi)
        if module <= 0:
            raise ValueError(
                f"{product.sku}: code {label.value!r} ({n} modules) cannot fit a {self.size} label"
            )
        if module < MIN_MODULE_MM - 1e-9:
            self.warnings.append(
                f"{product.sku}: bar module is {module:.3f} mm (< {MIN_MODULE_MM} mm) on a "
                f"{self.size} label; may not scan reliably. Use a shorter SKU/lot or a wider label"
            )
        module_pt = module * mm
        start = x0 + (w - n * module_pt) / 2
        if self.printer_dpi:  # align the first bar to the printer's dot grid
            dot = 72 / self.printer_dpi
            start = round(start / dot) * dot

        c.setFillGray(0)
        i = 0
        while i < n:
            if label.modules[i] == "1":
                j = i
                while j < n and label.modules[j] == "1":
                    j += 1
                c.rect(start + i * module_pt, bars_bottom, (j - i) * module_pt, bar_h, stroke=0, fill=1)
                i = j
            else:
                i += 1

    def render(self, products: list[Product], path: Path) -> None:
        labels = []
        for p in products:
            value = self.symbology.encode(p)
            labels.append(_Label(p, value, self.symbology.modules(value)))

        w, h = self.size.width_mm * mm, self.size.height_mm * mm
        if self.page == "label":
            c = Canvas(str(path), pagesize=(w, h))
            for label in labels:
                self._draw_label(c, 0, 0, label)
                c.showPage()
        else:
            page_w, page_h = PAGE_SIZES[self.page]
            margin, gap = 10 * mm, 2 * mm
            cols = int((page_w - 2 * margin + gap) // (w + gap))
            rows = int((page_h - 2 * margin + gap) // (h + gap))
            if cols < 1 or rows < 1:
                raise ValueError(f"a {self.size} label does not fit on a {self.page} page")
            c = Canvas(str(path), pagesize=(page_w, page_h))
            per_page = cols * rows
            for idx, label in enumerate(labels):
                if idx and idx % per_page == 0:
                    c.showPage()
                slot = idx % per_page
                x = margin + (slot % cols) * (w + gap)
                y = page_h - margin - (slot // cols + 1) * (h + gap) + gap
                c.setStrokeGray(0.8)
                c.setLineWidth(0.3)
                c.rect(x, y, w, h, stroke=1, fill=0)  # cut guide
                self._draw_label(c, x, y, label)
            c.showPage()
        c.setTitle("Product labels")
        c.save()
