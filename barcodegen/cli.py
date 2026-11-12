"""Command line interface: ``python -m barcodegen generate products.csv``."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from barcodegen import __version__
from barcodegen.generate import check_products, generate
from barcodegen.labels import PAGE_SIZES, parse_label_size
from barcodegen.products import InputError, load_products
from barcodegen.symbology import SYMBOLOGIES, get_symbology


def _label_size(text: str):
    try:
        return parse_label_size(text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def _dpi(text: str) -> int:
    value = int(text)
    if value < 300:
        raise argparse.ArgumentTypeError("must be at least 300")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="barcodegen", description="Generate product barcodes and printable labels from a CSV."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p: argparse.ArgumentParser) -> None:
        p.add_argument("csv", type=Path, help="product CSV (UTF-8): sku,name[,lot,expiry]")
        p.add_argument("--symbology", choices=sorted(SYMBOLOGIES), default="code128")
        p.add_argument("--lot-separator", default="/", help="character between SKU and lot (default: /)")
        p.add_argument("--gs1-prefix", help="GS1 company prefix (required for --symbology ean13)")

    gen = sub.add_parser("generate", help="create barcodes, labels.pdf and manifest.csv")
    common(gen)
    gen.add_argument("-o", "--output-dir", type=Path, default=Path("output"))
    gen.add_argument("--label-size", type=_label_size, default="50x30", help="WIDTHxHEIGHT in mm (default: 50x30)")
    gen.add_argument(
        "--page",
        choices=["label", *PAGE_SIZES],
        default="label",
        help="'label' = one label per page (thermal printers, default); a4/letter = grid sheet",
    )
    gen.add_argument("--printer-dpi", type=int, default=300, help="label printer resolution, bars snap to its dots (default: 300; 0 = don't snap)")
    gen.add_argument("--dpi", type=_dpi, default=600, help="PNG resolution, >= 300 (default: 600)")
    gen.add_argument("--strict", action="store_true", help="treat warnings as errors")

    val = sub.add_parser("validate", help="only check the CSV")
    common(val)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        symbology = get_symbology(args.symbology, lot_separator=args.lot_separator, gs1_prefix=args.gs1_prefix)
        products = load_products(args.csv)
        if args.command == "validate":
            warnings = check_products(products, symbology)
            for w in warnings:
                print(f"warning: {w}", file=sys.stderr)
            print(f"OK: {len(products)} products in {args.csv}")
            return 0

        result = generate(
            products,
            symbology,
            args.output_dir,
            args.label_size,
            page=args.page,
            printer_dpi=args.printer_dpi or None,
            image_dpi=args.dpi,
        )
    except InputError as exc:
        print(f"error: {args.csv} has {len(exc.errors)} problem(s):", file=sys.stderr)
        for e in exc.errors:
            print(f"  - {e}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    for w in result.warnings:
        print(f"warning: {w}", file=sys.stderr)
    print(f"Generated {result.count} barcodes in {result.barcodes_dir}/")
    print(f"Labels:   {result.labels_pdf}")
    print(f"Manifest: {result.manifest}")
    if args.strict and result.warnings:
        print("error: warnings present and --strict was given", file=sys.stderr)
        return 1
    return 0
