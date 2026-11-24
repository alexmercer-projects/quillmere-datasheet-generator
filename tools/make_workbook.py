#!/usr/bin/env python3
"""Regenerate the styled example workbook from its source CSV."""

import argparse
from pathlib import Path
import sys

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasheets.data import ROOT, read_products
from datasheets.validate import FIELDS, parse_number, validate_products

PAPER, TINT, INK, GOLD, LINE = "FBFAF6", "F0EEE4", "243534", "794C18", "D6D8CC"
WIDTHS = {
    "description": 68, "tagline": 47, "sku": 17, "name": 19, "family": 20,
    "housing_material": 24, "finishes": 32, "mounting": 36, "operating_temp_c": 21,
    "certifications_placeholder": 30, "image": 24, "accessories": 50, "notes": 62,
}


def fill(color):
    return PatternFill("solid", fgColor=color)


def header(cell):
    cell.font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
    cell.fill = fill(INK)
    cell.alignment = Alignment(vertical="center")


def text_cell(cell, value):
    cell.value = value
    cell.data_type = "s"


def make_workbook(csv_path, output):
    products = read_products(csv_path)
    issues = validate_products(products, ROOT / "assets/products")
    errors = [issue for issue in issues if issue.severity == "error"]
    if not products or errors:
        raise ValueError("The source CSV must have valid product rows. "
                         + " ".join(f"Row {issue.row}, {issue.field}. {issue.message}" for issue in errors))

    book = Workbook()
    book.properties.title = "Quillmere Lighting Co. / Example product data"
    book.properties.subject = "Concept demo with example fixture data and ratings"
    sheet = book.active
    sheet.title = "Products"
    sheet.sheet_view.showGridLines = False
    sheet.sheet_view.zoomScale = 85
    sheet.freeze_panes = "C2"
    sheet.row_dimensions[1].height = 29
    for column, key in enumerate(FIELDS, start=1):
        cell = sheet.cell(1, column, key)
        header(cell)
        sheet.column_dimensions[get_column_letter(column)].width = WIDTHS.get(key, max(13, len(key) + 3))

    prior_family = None
    for number, row in enumerate(products, start=2):
        family = row.cells["family"]
        family_start = family != prior_family
        sheet.row_dimensions[number].height = 43
        for column, (key, rule) in enumerate(FIELDS.items(), start=1):
            cell = sheet.cell(number, column)
            value = row.cells.get(key, "")
            if rule.bounds and value:
                numeric = parse_number(value, rule.unit)
                cell.value = int(numeric) if numeric == numeric.to_integral_value() else float(numeric)
                cell.number_format = "0" if rule.whole else "0.##"
            else:
                text_cell(cell, value)
            cell.alignment = Alignment(vertical="center", wrap_text=True)
            cell.fill = fill(PAPER if number % 2 == 0 else TINT)
            cell.font = Font(name="Calibri", size=11, bold=column <= 2, color=GOLD if column == 1 else INK)
            if family_start:
                cell.border = Border(top=Side(style="thin", color=LINE))
        prior_family = family
    sheet.auto_filter.ref = sheet.dimensions

    guide = book.create_sheet("Read me")
    guide.sheet_view.showGridLines = False
    guide.column_dimensions["A"].width = 32
    guide.column_dimensions["B"].width = 86
    guide.merge_cells("A1:B1")
    guide["A1"] = "Quillmere Lighting Co. / Concept demo"
    header(guide["A1"])
    guide.row_dimensions[1].height = 32
    guide.merge_cells("A2:B2")
    guide["A2"] = "Every product, specification and rating in this workbook is example data."
    guide["A2"].font = Font(name="Calibri", italic=True, color=GOLD)
    guide.merge_cells("A3:B3")
    guide["A3"] = "Use one row per fixture. Keep the Products header and regenerate this workbook from the CSV."
    for row_number, values in enumerate(
        [("Column", "Entry rules"), *(
            (field, rule.guidance + (
                " Required." if rule.required else ""
            )) for field, rule in FIELDS.items()
        )], start=5,
    ):
        guide.row_dimensions[row_number].height = 22
        for column, value in enumerate(values, start=1):
            cell = guide.cell(row_number, column, value)
            if row_number == 5:
                header(cell)
            else:
                cell.fill = fill(PAPER if row_number % 2 == 0 else TINT)
                cell.alignment = Alignment(vertical="center", wrap_text=True)
                cell.font = Font(name="Calibri", bold=column == 1, color=INK)
    guide.freeze_panes = "A6"
    output.parent.mkdir(parents=True, exist_ok=True)
    book.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=ROOT / "data/quillmere-products.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data/quillmere-products.xlsx")
    args = parser.parse_args()
    make_workbook(args.csv, args.output)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
