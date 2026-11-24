#!/usr/bin/env python3
"""Publish the static portfolio demo from the generated PDFs and workbook."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import csv
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from datasheets.data import ROOT, read_products
from datasheets.pdf import print_document, run_poppler
from datasheets.render import MARK, Markup, render, sheet_html
from generate import CATALOG_NAME, DEFAULT_ASSETS, DEFAULT_DATE, DEFAULT_REVISION, DEFAULT_TEMPLATE

DOCS = ROOT / "docs"
OUTPUT = ROOT / "output"
PRODUCTS = ROOT / "data/quillmere-products.csv"
BAD_FIXTURE = ROOT / "tests/fixtures/bad-products.csv"
SITE_TEMPLATE = ROOT / "tools/docs_index.html"
FEATURED = "QL-BOL-42"
EXAMPLE_NAME = "example-validation-report"


def rasterize(pdf, destination, width, work, crop=None):
    prefix = work / destination.stem
    run_poppler("pdftoppm", "-f", 1, "-l", 1, "-singlefile", "-scale-to-x", width,
                "-scale-to-y", -1, "-png", pdf, prefix)
    with Image.open(prefix.with_suffix(".png")) as png:
        image = png.convert("RGB")
    if crop:
        image = image.crop(tuple(round(p * image.width / 816) for p in crop))
        image = ImageOps.contain(image, (640, 380), Image.Resampling.LANCZOS)
        image = ImageOps.pad(image, (640, 380), color="#fbfaf6")
    image.save(destination, "WEBP", quality=87, method=6)


def make_example(work):
    work.mkdir()
    source = DEFAULT_TEMPLATE.read_text(encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(ROOT / "generate.py"), str(BAD_FIXTURE), "--strict", "--output", str(work)],
        text=True, capture_output=True, timeout=120,
    )
    report_path = work / "validation-report.json"
    if result.returncode != 1 or not report_path.is_file():
        raise ValueError(f"The bad-data fixture did not fail as expected. {result.stdout}{result.stderr}")

    report = json.loads(report_path.read_text(encoding="utf-8"))
    overflow = next((issue for issue in report["issues"] if issue["code"] == "overflow"), None)
    if overflow is None:
        raise ValueError(f"Expected a real overflow error in the bad-data fixture. {result.stdout}")

    row = next(row for row in read_products(BAD_FIXTURE) if row.number == overflow["row"])
    rendered = sheet_html(source, DEFAULT_TEMPLATE, row, DEFAULT_ASSETS, 6, DEFAULT_REVISION, DEFAULT_DATE)
    before = work / "before.pdf"
    print_document(rendered, before, work / "overflow-print")
    crop = (38, 120, 386, 362)
    rasterize(before, work / "overflow-before.webp", 1450, work, crop)
    rasterize(OUTPUT / f"sheets/{FEATURED}.pdf", work / "overflow-after.webp", 1450, work, crop)
    shutil.move(str(work / "validation-report.md"), str(DOCS / "files" / f"{EXAMPLE_NAME}.md"))
    for name in ("overflow-before.webp", "overflow-after.webp"):
        shutil.move(str(work / name), str(DOCS / "img" / name))
    return report


def example_report(work, refresh):
    # Use the checked-in example for a docs-only build, and regenerate it whenever its inputs change.
    sources = (BAD_FIXTURE, DEFAULT_TEMPLATE, DEFAULT_TEMPLATE.with_suffix(".css"),
               PRODUCTS, ROOT / "generate.py", *sorted((ROOT / "datasheets").glob("*.py")))
    digest = sha256()
    for path in sources:
        digest.update(path.read_bytes())
    signature = digest.hexdigest()
    cache = DOCS / "files" / f"{EXAMPLE_NAME}.json"
    payload = json.loads(cache.read_text(encoding="utf-8")) if cache.is_file() else {}
    artifacts = (
        DOCS / "files" / f"{EXAMPLE_NAME}.md",
        DOCS / "img/overflow-before.webp", DOCS / "img/overflow-after.webp",
    )
    if refresh or payload.get("signature") != signature or not all(path.is_file() for path in artifacts):
        payload = {"signature": signature, **make_example(work)}
        cache.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return payload


def make_template_zip():
    with ZipFile(DOCS / "files/quillmere-template.zip", "w", ZIP_DEFLATED) as bundle:
        for path in (DEFAULT_TEMPLATE, DEFAULT_TEMPLATE.with_suffix(".css"), *sorted((DOCS / "fonts").iterdir())):
            bundle.write(path, path.relative_to(ROOT))


def write_index(products, bad_report):
    families = list(dict.fromkeys(row.cells["family"] for row in products))
    featured = next(row.cells for row in products if row.sku == FEATURED)
    summary = bad_report["summary"]
    examples = [
        next(issue for issue in bad_report["issues"] if issue["code"] == code)
        for code in ("duplicate", "unit", "overflow", "optional")
    ]
    downloads = [
        (f"files/{CATALOG_NAME}", "PDF", "Product catalog", "18 pages · cover, contents and all sheets"),
        ("files/quillmere-products.xlsx", "XLSX", "Product workbook", "16 rows and a Read me tab"),
        ("files/quillmere-products.csv", "CSV", "Source spreadsheet", "The same rows in plain text"),
        ("files/quillmere-template.zip", "ZIP", "Print template", "HTML, CSS and local fonts"),
        (f"sheets/{FEATURED}.pdf", "PDF", "Strata 420 sheet", "Sample bollard · one page"),
        ("sheets/QL-WAL-12.pdf", "PDF", "Cairn 120 sheet", "Sample wall sconce · one page"),
        ("files/validation-report.md", "MD", "Validation report", "Results for the published run"),
    ]
    source = SITE_TEMPLATE.read_text(encoding="utf-8")
    html = render(source, {
        "mark": Markup(MARK),
        "featured": featured,
        "excerpt": [products[index].cells for index in (0, 3, 6, 9)],
        "families": [{"name": name} for name in families],
        "products": [row.cells for row in products],
        "bad_summary": f"{summary['products']} rows checked · {summary['errors']} errors · {summary['warnings']} warning.",
        "findings": examples,
        "downloads": [{"href": href, "type": kind, "label": label, "detail": detail}
                      for href, kind, label, detail in downloads],
    })
    (DOCS / "index.html").write_text(html, encoding="utf-8")


def build_docs(refresh):
    products = read_products(PRODUCTS)
    workbook = PRODUCTS.with_suffix(".xlsx")
    if products != read_products(workbook):
        raise ValueError("The example CSV and workbook differ. Run tools/make_workbook.py and regenerate the PDFs.")
    with (OUTPUT / "manifest.csv").open(encoding="utf-8", newline="") as source:
        manifest = list(csv.DictReader(source))
    if [(item["sku"], item["name"]) for item in manifest] != [(row.sku, row.cells["name"]) for row in products]:
        raise ValueError("The manifest does not match the example spreadsheet. Run the full strict PDF generation first.")
    report = json.loads((OUTPUT / "validation-report.json").read_text(encoding="utf-8"))
    if report["summary"]["errors"] or report["summary"]["catalog_pages"] != len(products) + 2:
        raise ValueError("The demo PDF run is incomplete. Run the full strict PDF generation first.")
    if any(item["status"] not in {"ok", "warning"} or item["pages"] != "1" for item in manifest):
        raise ValueError("The demo manifest must contain a valid one-page PDF for every fixture.")
    for subdir in ("files", "img", "sheets"):
        (DOCS / subdir).mkdir(exist_ok=True)
    for path in (PRODUCTS, workbook, OUTPUT / CATALOG_NAME, OUTPUT / "validation-report.md"):
        shutil.copyfile(path, DOCS / "files" / path.name)
    make_template_zip()
    with TemporaryDirectory(prefix="quillmere-docs-") as temporary:
        work = Path(temporary)
        for row in products:
            filename = f"sheets/{row.sku}.pdf"
            shutil.copyfile(OUTPUT / filename, DOCS / filename)
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = [
                pool.submit(rasterize, DOCS / f"sheets/{row.sku}.pdf", DOCS / f"img/{row.sku}.webp", 600, work)
                for row in products
            ]
            jobs.append(pool.submit(rasterize, DOCS / f"sheets/{FEATURED}.pdf", DOCS / "img/featured.webp", 960, work))
            for job in jobs:
                job.result()
        report = example_report(work / "example", refresh)
        write_index(products, report)
    print(f"Built {DOCS / 'index.html'} with {len(products)} PDF previews.")
    print(f"Site files: {sum(path.stat().st_size for path in DOCS.rglob('*') if path.is_file()) / 1_000_000:.2f} MB.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh-examples", action="store_true", help="Regenerate the bad-data report and overflow crops")
    args = parser.parse_args()
    try:
        build_docs(args.refresh_examples)
    except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as error:
        parser.exit(1, f"ERROR {error}\n")


if __name__ == "__main__":
    main()
