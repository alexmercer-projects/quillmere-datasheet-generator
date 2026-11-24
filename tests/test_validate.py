from dataclasses import replace
from decimal import Decimal
import unittest

from datasheets.data import ROOT, read_products
from datasheets.validate import InvalidValue, parse_number, parse_temperature, validate_products

ASSETS = ROOT / "assets/products"
CSV = ROOT / "data/quillmere-products.csv"


class DataTests(unittest.TestCase):
    def test_csv_and_workbook_parity(self):
        rows = read_products(CSV)
        self.assertEqual(rows, read_products(CSV.with_suffix(".xlsx")))
        self.assertEqual(len(rows), 16)
        self.assertEqual(len({row.cells["family"] for row in rows}), 6)
        self.assertEqual(validate_products(rows, ASSETS), [])

    def test_bad_fixture(self):
        rows = read_products(ROOT / "tests/fixtures/bad-products.csv")
        issues = validate_products(rows, ASSETS)
        observed = {(issue.field, issue.code, issue.severity) for issue in issues}
        expected = {
            ("name", "required", "error"), ("sku", "duplicate", "error"),
            ("tagline", "length", "error"), ("notes", "length", "error"),
            ("lumens", "number", "error"), ("cri", "range", "error"),
            ("width_mm", "unit", "error"), ("weight_kg", "unit", "error"),
            ("operating_temp_c", "unit", "error"), ("image", "image", "error"),
            ("finishes", "finish", "error"), ("cct_k", "format", "error"),
            ("ip_rating", "format", "error"), ("efficacy", "efficacy", "error"),
            ("accessories", "optional", "warning"),
        }
        self.assertTrue(expected <= observed, expected - observed)
        self.assertFalse(any(issue.row == 4 for issue in issues))

    def test_additional_field_limits_and_formats(self):
        original = read_products(CSV)[0]
        cases = [
            ("sku", "../../light", "format"), ("name", "a" * 49, "length"),
            ("description", "a" * 421, "length"), ("watts", "0", "range"),
            ("lumens", "10.5", "range"), ("beam_angle_deg", "181", "range"),
            ("warranty_years", "1.5", "range"), ("cct_k", "2700/2700", "format"),
            ("operating_temp_c", "40 to 20", "range"), ("image", "../ql-wal-12.svg", "image"),
            ("finishes", "Graphite|Graphite", "duplicate"), ("ik_rating", "IK11", "format"),
            ("certifications_placeholder", "Listed", "format"),
        ]
        for field, value, code in cases:
            with self.subTest(field=field, value=value):
                row = replace(original, cells={**original.cells, field: value})
                self.assertIn((field, code), {(i.field, i.code) for i in validate_products([row], ASSETS)})

    def test_duplicate_still_detected_when_selecting_one(self):
        rows = read_products(ROOT / "tests/fixtures/bad-products.csv")
        self.assertEqual(sum(i.code == "duplicate" for i in validate_products(rows, ASSETS, "QL-WAL-12")), 2)

    def test_efficacy_tolerance(self):
        original = read_products(CSV)[0]
        for value, valid in (("78.4", True), ("81.6", True), ("81.61", False)):
            row = replace(original, cells={**original.cells, "efficacy": value})
            self.assertEqual(not validate_products([row], ASSETS), valid)


class UnitTests(unittest.TestCase):
    def test_numbers_in_expected_unit(self):
        for value, unit, expected in (("120", "mm", "120"), ("120mm", "mm", "120"),
                                      ("3.5 KG", "kg", "3.5"), (" .5 ", "W", "0.5")):
            self.assertEqual(parse_number(value, unit), Decimal(expected))

    def test_wrong_units_and_invalid_numbers(self):
        for value, unit, code in (("120in", "mm", "unit"), ("3 lbs", "kg", "unit"),
                                  ("120 cm", "mm", "unit"), ("NaN", "mm", "number"),
                                  ("infinite", "kg", "number"), ("1,000", "lm", "number")):
            with self.subTest(value=value), self.assertRaises(InvalidValue) as caught:
                parse_number(value, unit)
            self.assertEqual(caught.exception.code, code)

    def test_temperature_range(self):
        self.assertEqual(parse_temperature("-25 °C to 45 C"), (-25, 45))
        for value, code in (("-4 to 120 F", "unit"), ("0 K to 45", "unit"),
                            ("45 to 20", "range"), ("hot to cold", "temperature")):
            with self.subTest(value=value), self.assertRaises(InvalidValue) as caught:
                parse_temperature(value)
            self.assertEqual(caught.exception.code, code)
