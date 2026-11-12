"""Barcode symbologies.

A symbology decides *what* gets encoded for a product and *how* it becomes bars.
Code 128 is the default. EAN-13 is a documented extension point for when the
company gets a GS1 prefix; it is not needed for internal identification.

To add a new symbology: subclass ``Symbology``, implement ``encode`` (and
optionally ``check``), and register it in ``SYMBOLOGIES``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import barcode
from barcode.base import Barcode

from barcodegen.products import Product


class Symbology(ABC):
    name: str  # registry key, e.g. "code128"
    barcode_class: str  # python-barcode class name

    @abstractmethod
    def encode(self, product: Product) -> str:
        """Return the exact value to encode for this product."""

    def check(self, product: Product) -> list[str]:
        """Return error messages if this product cannot be encoded."""
        return []

    def notes(self, product: Product) -> list[str]:
        """Return non-fatal warnings for this product."""
        return []

    def make(self, value: str, writer=None) -> Barcode:
        return barcode.get_barcode_class(self.barcode_class)(value, writer=writer)

    def modules(self, value: str) -> str:
        """Bar pattern as a string of '1' (bar) and '0' (space), one char per module."""
        return "".join(self.make(value).build())


class Code128(Symbology):
    """Code 128: any printable ASCII. Encodes ``SKU`` or ``SKU<sep>LOT``."""

    name = "code128"
    barcode_class = "code128"

    def __init__(self, lot_separator: str = "/"):
        if len(lot_separator) != 1 or not (32 < ord(lot_separator) < 127):
            raise ValueError("lot separator must be a single printable ASCII character")
        self.lot_separator = lot_separator

    def encode(self, product: Product) -> str:
        if product.lot:
            return f"{product.sku}{self.lot_separator}{product.lot}"
        return product.sku

    def check(self, product: Product) -> list[str]:
        if self.lot_separator in product.sku or self.lot_separator in product.lot:
            return [
                f"line {product.line}: sku/lot must not contain the lot separator "
                f"{self.lot_separator!r}, or the code cannot be split back into sku and lot"
            ]
        return []


def ean13_check_digit(digits12: str) -> str:
    """GS1 mod-10 check digit for the first 12 digits of an EAN-13."""
    if len(digits12) != 12 or not digits12.isdigit():
        raise ValueError(f"expected 12 digits, got {digits12!r}")
    # From the right, positions alternate weight 3 and 1 (rightmost has weight 3).
    total = sum(int(d) * (3 if i % 2 == 0 else 1) for i, d in enumerate(reversed(digits12)))
    return str((10 - total % 10) % 10)


class Ean13(Symbology):
    """EAN-13 / GTIN-13 built from a GS1 company prefix + per-product item reference.

    Requires an ``item_ref`` column in the CSV. GTIN = prefix + item_ref (zero
    padded to fill 12 digits) + check digit. Lot/expiry cannot be encoded in
    EAN-13; they are still printed as text on the label.

    Only use numbers assigned under your own GS1 licence.
    """

    name = "ean13"
    barcode_class = "ean13"

    def __init__(self, company_prefix: str | None):
        if not company_prefix:
            raise ValueError("EAN-13 needs a GS1 company prefix (--gs1-prefix)")
        if not company_prefix.isdigit() or not 6 <= len(company_prefix) <= 11:
            raise ValueError("GS1 company prefix must be 6 to 11 digits")
        self.company_prefix = company_prefix

    @property
    def item_ref_digits(self) -> int:
        return 12 - len(self.company_prefix)

    def check(self, product: Product) -> list[str]:
        ref = product.item_ref
        if not ref:
            return [f"line {product.line}: EAN-13 needs an 'item_ref' value (sku {product.sku})"]
        if not ref.isdigit() or len(ref) > self.item_ref_digits:
            return [
                f"line {product.line}: item_ref {ref!r} must be up to "
                f"{self.item_ref_digits} digits with prefix {self.company_prefix}"
            ]
        return []

    def notes(self, product: Product) -> list[str]:
        if product.lot:
            return [f"{product.sku}: EAN-13 cannot carry the lot; it is only printed as text"]
        return []

    def encode(self, product: Product) -> str:
        base = self.company_prefix + product.item_ref.zfill(self.item_ref_digits)
        return base + ean13_check_digit(base)

    def make(self, value: str, writer=None) -> Barcode:
        # python-barcode recomputes the check digit from the first 12 digits.
        return barcode.get_barcode_class(self.barcode_class)(value[:12], writer=writer)


SYMBOLOGIES = {"code128": Code128, "ean13": Ean13}


def get_symbology(name: str, *, lot_separator: str = "/", gs1_prefix: str | None = None) -> Symbology:
    if name == "code128":
        return Code128(lot_separator)
    if name == "ean13":
        return Ean13(gs1_prefix)
    raise ValueError(f"unknown symbology {name!r} (choose from {', '.join(SYMBOLOGIES)})")
