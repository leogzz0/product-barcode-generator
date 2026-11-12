"""Reading and validating the product CSV."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

REQUIRED_COLUMNS = ("sku", "name")
OPTIONAL_COLUMNS = ("lot", "expiry", "item_ref")

# SKUs become file names and barcode content, so keep them to a safe ASCII set.
SKU_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
LOT_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


class InputError(Exception):
    """The input CSV cannot be used. Holds one message per problem found."""

    def __init__(self, errors: list[str]):
        self.errors = errors
        super().__init__("\n".join(errors))


@dataclass(frozen=True)
class Product:
    line: int  # line number in the CSV, for error messages
    sku: str
    name: str
    lot: str = ""
    expiry: str = ""
    item_ref: str = ""  # only used by EAN-13 (see symbology.py)


def _non_ascii(value: str) -> str:
    return ", ".join(sorted({repr(c) for c in value if ord(c) > 127}))


def load_products(path: str | Path) -> list[Product]:
    """Load and validate products. Raises InputError listing every problem."""
    path = Path(path)
    try:
        # utf-8-sig transparently drops the BOM that Excel adds to CSV exports.
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        raise InputError([f"{path}: file not found"]) from None
    except UnicodeDecodeError as exc:
        raise InputError(
            [
                f"{path}: not valid UTF-8 (byte {exc.start}). "
                "Save the file as 'CSV UTF-8' and try again."
            ]
        ) from None

    reader = csv.DictReader(text.splitlines())
    header = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in REQUIRED_COLUMNS if c not in header]
    if missing:
        raise InputError(
            [f"{path}: missing required column(s): {', '.join(missing)} (found: {', '.join(header) or 'nothing'})"]
        )
    reader.fieldnames = header

    errors: list[str] = []
    products: list[Product] = []
    seen: dict[str, int] = {}  # lower-cased sku -> line

    for row in reader:
        line = reader.line_num
        if None in row:
            errors.append(f"line {line}: more values than columns in the header")
        values = {k: (v or "").strip() for k, v in row.items() if k is not None}
        if not any(values.values()):
            continue  # ignore fully blank rows

        sku, name = values.get("sku", ""), values.get("name", "")
        lot, expiry = values.get("lot", ""), values.get("expiry", "")
        item_ref = values.get("item_ref", "")

        if not sku:
            errors.append(f"line {line}: 'sku' is empty")
        elif not sku.isascii():
            errors.append(f"line {line}: sku {sku!r} has non-ASCII characters ({_non_ascii(sku)})")
        elif not SKU_PATTERN.match(sku):
            errors.append(
                f"line {line}: sku {sku!r} may only contain letters, digits, '-', '_' and '.' "
                "and must start with a letter or digit"
            )
        else:
            key = sku.lower()  # case-insensitive: file names collide on macOS/Windows
            if key in seen:
                errors.append(f"line {line}: duplicate sku {sku!r} (first seen on line {seen[key]})")
            else:
                seen[key] = line

        if not name:
            errors.append(f"line {line}: 'name' is empty" + (f" (sku {sku})" if sku else ""))

        if lot:
            if not lot.isascii():
                errors.append(f"line {line}: lot {lot!r} has non-ASCII characters ({_non_ascii(lot)})")
            elif not LOT_PATTERN.match(lot):
                errors.append(
                    f"line {line}: lot {lot!r} may only contain letters, digits, '-', '_' and '.'"
                )

        products.append(Product(line, sku, name, lot, expiry, item_ref))

    if not errors and not products:
        errors.append(f"{path}: no products found")
    if errors:
        raise InputError(errors)
    return products
