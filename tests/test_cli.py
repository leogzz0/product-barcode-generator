import csv

import pytest
from PIL import Image

from barcodegen.cli import main


def test_generate_end_to_end(write_csv, tmp_path, capsys):
    path = write_csv(
        "sku,name,lot,expiry\n"
        "NVA-ORE-07,Nieve de vainilla con Oreo 7 oz,,\n"
        "HGG-FRE-12,Helado de yogurt griego con fresa y granola 12 oz,L1,2027-01-01\n"
    )
    out = tmp_path / "output"
    assert main(["generate", str(path), "-o", str(out), "--label-size", "60x30"]) == 0

    for sku in ("NVA-ORE-07", "HGG-FRE-12"):
        assert (out / "barcodes" / f"{sku}.png").is_file()
        assert (out / "barcodes" / f"{sku}.svg").read_text().lstrip().startswith("<?xml")
    assert (out / "labels.pdf").read_bytes().startswith(b"%PDF")

    with (out / "manifest.csv").open(encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert [(r["sku"], r["encoded_value"], r["png_file"]) for r in rows] == [
        ("NVA-ORE-07", "NVA-ORE-07", "barcodes/NVA-ORE-07.png"),
        ("HGG-FRE-12", "HGG-FRE-12/L1", "barcodes/HGG-FRE-12.png"),
    ]
    assert "Generated 2 barcodes" in capsys.readouterr().out


def test_png_is_high_resolution(write_csv, tmp_path):
    path = write_csv("sku,name\nA-1,Uno\n")
    assert main(["generate", str(path), "-o", str(tmp_path / "o"), "--dpi", "300"]) == 0
    image = Image.open(tmp_path / "o" / "barcodes" / "A-1.png")
    assert image.info["dpi"][0] == pytest.approx(300, abs=0.01)


def test_invalid_csv_fails_with_clear_message(write_csv, tmp_path, capsys):
    path = write_csv("sku,name\nA-1,Uno\nA-1,Dos\nÑ-1,Tres\n")
    out = tmp_path / "output"
    assert main(["generate", str(path), "-o", str(out)]) == 1
    err = capsys.readouterr().err
    assert "2 problem(s)" in err
    assert "line 3: duplicate sku 'A-1'" in err
    assert "non-ASCII" in err
    assert not out.exists()  # nothing written when input is invalid


def test_validate_command(sample_csv, capsys):
    assert main(["validate", str(sample_csv)]) == 0
    assert "OK: 34 products" in capsys.readouterr().out


def test_ean13_without_prefix_fails(sample_csv, capsys):
    assert main(["validate", str(sample_csv), "--symbology", "ean13"]) == 1
    assert "GS1 company prefix" in capsys.readouterr().err


def test_ean13_end_to_end(write_csv, tmp_path):
    path = write_csv("sku,name,item_ref\nA-1,Uno,1\n")
    out = tmp_path / "o"
    assert main(["generate", str(path), "-o", str(out), "--symbology", "ean13", "--gs1-prefix", "7501234"]) == 0
    rows = list(csv.DictReader((out / "manifest.csv").open()))
    assert rows[0]["encoded_value"] == "7501234000017"


def test_strict_turns_warnings_into_failure(write_csv, tmp_path):
    path = write_csv("sku,name,lot\nCRM-NVA-ORE-07,Uno,L261112\n")
    assert main(["generate", str(path), "-o", str(tmp_path / "o")]) == 0
    assert main(["generate", str(path), "-o", str(tmp_path / "o"), "--strict"]) == 1


def test_bad_label_size_is_a_usage_error(sample_csv):
    with pytest.raises(SystemExit) as exc:
        main(["generate", str(sample_csv), "--label-size", "big"])
    assert exc.value.code == 2
