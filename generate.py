#!/usr/bin/env python3
"""Validate a product spreadsheet and build its print-ready PDF files."""

import argparse
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import csv
from datetime import date
from pathlib import Path
import re
import sys
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException

from datasheets.catalog import catalog_html, intro_pages
from datasheets.data import ROOT, read_products
from datasheets.pdf import BrowserError, pdf_pages, print_document, run_poppler
from datasheets.render import sheet_html
from datasheets.report import write_reports
from datasheets.validate import FIELDS, Issue, validate_products

CATALOG_NAME = "quillmere-catalog-DEMO.pdf"
DEFAULT_DATE = "2026-11-23"
DEFAULT_REVISION = "01"
DEFAULT_TEMPLATE = ROOT / "template/datasheet.html"
DEFAULT_ASSETS = ROOT / "assets/products"


def check_print(result, expected):
    findings = []
    if result.pages != expected:
        findings.append(("pagination", "", f"Expected {expected} PDF page(s); found {result.pages}."))
    for box in result.overflow:
        dimensions = f"{box['width']} px wide, {box['height']} px tall"
        findings.append(("overflow", box["field"], f"Text exceeds the print box by {dimensions}."))
    for image in result.broken:
        findings.append(("broken_image", "image", f"Chrome could not load {image!r}."))
    for font in result.fonts:
        findings.append(("font", "", f"Chrome could not load the {font} font."))
    return findings


def render_one(row, page, template, source, assets, stage, revision, issued):
    file = stage / "sheets" / f"{row.sku}.pdf"
    try:
        html = sheet_html(source, template, row, assets, page, revision, issued)
        result = print_document(html, file, stage / f"render-{row.number}")
        findings = check_print(result, 1)
        if not result.checked:
            findings.append(("fit_missing", "", "Mark template boxes that should be checked with data-fit."))
    except (BrowserError, ValueError, OSError) as error:
        findings = [("render", "", str(error))]
    if findings:
        file.unlink(missing_ok=True)
    return [Issue("error", code, message, field, row.number, row.sku)
            for code, field, message in findings]


def render_sheets(rows, template, source, assets, stage, revision, issued, workers):
    valid = list(rows)
    issued_pages = {}
    issues = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        while True:
            jobs = [
                (row, page, pool.submit(render_one, row, page, template, source, assets, stage, revision, issued))
                for page, row in enumerate(valid, start=intro_pages(len(valid)) + 1) if issued_pages.get(row.number) != page
            ]
            if not jobs:
                break
            for row, page, future in jobs:
                findings = future.result()
                if findings:
                    valid.remove(row)
                    issues.extend(findings)
                else:
                    issued_pages[row.number] = page
    return valid, issues


def render_catalog(rows, assets, stage, revision, issued):
    intro = stage / "intro.pdf"
    try:
        result = print_document(catalog_html(rows, assets, revision, issued), intro, stage / "render-catalog")
        front_matter = intro_pages(len(rows))
        findings = check_print(result, front_matter)
        if findings:
            return 0, [Issue("error", code, message, field) for code, field, message in findings]
        target = stage / CATALOG_NAME
        run_poppler("pdfunite", intro, *(stage / "sheets" / f"{row.sku}.pdf" for row in rows), target)
        count = pdf_pages(target)
        if count != len(rows) + front_matter:
            target.unlink()
            raise BrowserError(f"Expected {len(rows) + front_matter} catalog pages; found {count}.")
        return count, []
    except (BrowserError, ValueError, OSError) as error:
        (stage / CATALOG_NAME).unlink(missing_ok=True)
        return 0, [Issue("error", "catalog", str(error))]


def publish(stage, output, manifest):
    previous = output / "manifest.csv"
    published = {item["file"] for item in manifest if item["file"]}
    stale = set()
    if previous.is_file():
        with previous.open(encoding="utf-8", newline="") as old:
            for row in csv.DictReader(old):
                if re.fullmatch(r"sheets/[A-Z0-9]+(?:-[A-Z0-9]+)*\.pdf", row.get("file") or ""):
                    stale.add(row["file"])
    (output / "sheets").mkdir(exist_ok=True)
    for name in published:
        (stage / name).replace(output / name)
    for name in stale - published:
        (output / name).unlink(missing_ok=True)
    if (stage / CATALOG_NAME).is_file():
        (stage / CATALOG_NAME).replace(output / CATALOG_NAME)
    else:
        (output / CATALOG_NAME).unlink(missing_ok=True)
    for name in ("validation-report.json", "validation-report.md", "manifest.csv"):
        (stage / name).replace(output / name)


def build(args):
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    issues = []
    load_failed = False
    try:
        all_rows = read_products(args.input)
        rows = [row for row in all_rows if args.only is None or row.sku == args.only]
        if not rows:
            message = f"No rows match SKU {args.only!r}." if args.only else "The spreadsheet has no product rows."
            issues.append(Issue("error", "empty", message))
        issues.extend(validate_products(all_rows, args.assets, args.only))
    except (ValueError, OSError, BadZipFile, InvalidFileException, csv.Error) as error:
        issues.append(Issue("error", "input", str(error)))
        rows = []
        load_failed = True

    blocked = {issue.row for issue in issues if issue.severity == "error"}
    with TemporaryDirectory(prefix=".quillmere-", dir=output) as temporary:
        stage = Path(temporary)
        (stage / "sheets").mkdir()
        valid = [row for row in rows if row.number not in blocked]
        catalog_pages = 0
        if valid:
            try:
                source = args.template.read_text(encoding="utf-8")
            except OSError as error:
                issues.append(Issue("error", "template", str(error)))
                valid = []
            else:
                valid, render_issues = render_sheets(
                    valid, args.template, source, args.assets, stage, args.revision, args.date, args.workers,
                )
                issues.extend(render_issues)
        if valid:
            catalog_pages, catalog_issues = render_catalog(valid, args.assets, stage, args.revision, args.date)
            issues.extend(catalog_issues)

        findings_by_row = defaultdict(set)
        for issue in issues:
            findings_by_row[issue.row].add(issue.severity)
        valid_rows = {row.number for row in valid}
        manifest = []
        for row in rows:
            filename = f"sheets/{row.sku}.pdf" if row.number in valid_rows else ""
            status = ("warning" if "warning" in findings_by_row[row.number] else "ok") if filename else "error"
            manifest.append({
                "sku": row.sku, "name": row.cells.get("name", ""), "file": filename,
                "pages": 1 if filename else 0, "bytes": (stage / filename).stat().st_size if filename else 0,
                "status": status,
            })
        issues.sort(key=lambda issue: (issue.row is None, issue.row or 0))
        summary = write_reports(stage, args.input, rows, issues, manifest, catalog_pages)
        publish(stage, output, manifest)
    for issue in issues:
        where = f"row {issue.row} {issue.sku}".rstrip() if issue.row else "run"
        field = f" / {issue.field}" if issue.field else ""
        print(f"{issue.severity.upper()} [{where}{field}] {issue.message}")
    print(f"{summary['sheets']}/{summary['products']} sheets written. Catalog: {catalog_pages} pages. "
          f"{summary['errors']} errors, {summary['warnings']} warnings.")
    print(f"Reports and manifest: {output}")
    return int(load_failed or (args.strict and summary["errors"] > 0))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Product CSV or XLSX")
    parser.add_argument("--strict", action="store_true", help="Exit nonzero if any errors are reported")
    parser.add_argument("--only", metavar="SKU", help="Build a single SKU")
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE, help="HTML template")
    parser.add_argument("--assets", type=Path, default=DEFAULT_ASSETS, help="Product image directory")
    parser.add_argument("--output", type=Path, default=ROOT / "output", help="Destination directory")
    parser.add_argument("--workers", type=int, default=4, help="Maximum simultaneous Chrome processes")
    parser.add_argument("--revision", default=DEFAULT_REVISION, help="Sheet revision, default %(default)s")
    parser.add_argument("--date", default=DEFAULT_DATE, help="Issue date as YYYY-MM-DD, default %(default)s")
    args = parser.parse_args(argv)
    if args.workers < 1:
        parser.error("--workers must be positive")
    if not re.fullmatch(r"[A-Za-z0-9.-]{1,12}", args.revision):
        parser.error("--revision must use 1 to 12 letters, digits, periods or hyphens")
    try:
        if date.fromisoformat(args.date).isoformat() != args.date:
            raise ValueError(args.date)
    except ValueError:
        parser.error("--date must use YYYY-MM-DD")
    try:
        return build(args)
    except (OSError, csv.Error) as error:
        print(f"ERROR {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
