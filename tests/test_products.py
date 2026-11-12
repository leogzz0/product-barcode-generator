import pytest

from barcodegen.products import InputError, load_products


def errors_for(path):
    with pytest.raises(InputError) as exc:
        load_products(path)
    return exc.value.errors


def test_loads_valid_csv(write_csv):
    path = write_csv(
        "sku,name,lot,expiry\n"
        "NVA-ORE-07,Nieve de vainilla con Oreo 7 oz,L261112,2027-02-12\n"
        "NVA-ORE-12,Nieve de vainilla con Oreo 12 oz,,\n"
    )
    products = load_products(path)
    assert [p.sku for p in products] == ["NVA-ORE-07", "NVA-ORE-12"]
    assert products[0].lot == "L261112"
    assert products[0].expiry == "2027-02-12"
    assert products[1].lot == ""


def test_optional_columns_may_be_absent(write_csv):
    products = load_products(write_csv("sku,name\nA-1,Producto A\n"))
    assert products[0].lot == "" and products[0].expiry == ""


def test_header_is_case_and_space_insensitive(write_csv):
    products = load_products(write_csv(" SKU , Name \nA-1, Producto A \n"))
    assert products[0].sku == "A-1" and products[0].name == "Producto A"


def test_accepts_excel_bom_and_utf8_names(write_csv):
    products = load_products(write_csv("﻿sku,name\nNYP-AVE-07,Nieve con proteína y avena\n"))
    assert products[0].sku == "NYP-AVE-07"
    assert products[0].name == "Nieve con proteína y avena"


def test_skips_blank_rows(write_csv):
    products = load_products(write_csv("sku,name\nA-1,Uno\n,\n\nA-2,Dos\n"))
    assert [p.sku for p in products] == ["A-1", "A-2"]


def test_missing_required_column(write_csv):
    (error,) = errors_for(write_csv("sku,nombre\nA-1,Uno\n"))
    assert "missing required column(s): name" in error


def test_duplicate_sku_reports_both_lines(write_csv):
    (error,) = errors_for(write_csv("sku,name\nA-1,Uno\nA-2,Dos\nA-1,Otra vez\n"))
    assert "line 4" in error and "duplicate sku 'A-1'" in error and "line 2" in error


def test_duplicate_sku_is_case_insensitive(write_csv):
    (error,) = errors_for(write_csv("sku,name\nabc-1,Uno\nABC-1,Dos\n"))
    assert "duplicate sku 'ABC-1'" in error


def test_empty_values(write_csv):
    errors = errors_for(write_csv("sku,name\n,Sin sku\nB-1,\n"))
    assert errors == ["line 2: 'sku' is empty", "line 3: 'name' is empty (sku B-1)"]


def test_non_ascii_sku(write_csv):
    (error,) = errors_for(write_csv("sku,name\nPROTEÍNA-1,Uno\n"))
    assert "non-ASCII" in error and "'Í'" in error


def test_sku_with_unsafe_characters(write_csv):
    (error,) = errors_for(write_csv("sku,name\nA/1,Uno\n"))
    assert "may only contain" in error


def test_non_ascii_lot(write_csv):
    (error,) = errors_for(write_csv("sku,name,lot\nA-1,Uno,LOTE-Ñ\n"))
    assert "lot 'LOTE-Ñ' has non-ASCII" in error


def test_all_errors_are_reported_at_once(write_csv):
    errors = errors_for(write_csv("sku,name\n,X\nA-1,\nA-1,Y\nñ,Z\n"))
    assert len(errors) == 4


def test_not_utf8(write_csv):
    (error,) = errors_for(write_csv("sku,name\nA-1,Proteína\n", encoding="latin-1"))
    assert "not valid UTF-8" in error


def test_missing_file(tmp_path):
    (error,) = errors_for(tmp_path / "nope.csv")
    assert "file not found" in error


def test_empty_file(write_csv):
    (error,) = errors_for(write_csv("sku,name\n"))
    assert "no products found" in error


def test_sample_catalog_is_valid(sample_csv):
    products = load_products(sample_csv)
    assert len(products) == 34
    sizes = [p.sku.rsplit("-", 1)[1] for p in products]
    assert sizes.count("07") == 17 and sizes.count("12") == 17
