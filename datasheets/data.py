"""Read a CSV or Excel workbook into the same row representation."""

import csv
from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Row:
    number: int
    cells: dict[str, str]

    @property
    def sku(self):
        return self.cells.get("sku", "")


def cell_text(value):
    return "" if value is None else str(value).strip()


def parse_rows(records):
    records = iter(records)
    header = [cell_text(value) for value in next(records, ())]
    while header and not header[-1]:
        header.pop()
    if not header or "" in header or len(set(header)) != len(header):
        raise ValueError("Expected a nonempty header with unique column names.")
    rows = []
    for number, record in enumerate(records, start=2):
        values = [cell_text(value) for value in record]
        if not any(values):
            continue
        if any(values[len(header):]):
            raise ValueError(f"Row {number} has values past the last column header.")
        values += [""] * (len(header) - len(values))
        rows.append(Row(number, dict(zip(header, values))))
    return rows


def read_products(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as source:
            return parse_rows(csv.reader(source, strict=True))
    if path.suffix.lower() == ".xlsx":
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet = workbook["Products"] if "Products" in workbook else workbook.active
            return parse_rows(sheet.values)
        finally:
            workbook.close()
    raise ValueError("Expected a .csv or .xlsx input file.")
