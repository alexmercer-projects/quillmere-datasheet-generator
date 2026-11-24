from dataclasses import replace
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from datasheets.data import ROOT, read_products
from datasheets.pdf import BrowserError, chrome, print_document
from datasheets.render import sheet_html
from generate import DEFAULT_ASSETS, DEFAULT_DATE, DEFAULT_REVISION, DEFAULT_TEMPLATE

BROWSER = os.environ.get("QUILLMERE_CHROME", "google-chrome")


@unittest.skipUnless(shutil.which(BROWSER) and shutil.which("pdfinfo"),
                     "Chrome and pdfinfo are required for PDF tests")
class PdfTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # A locked-down execution environment can provide Chrome but deny its startup IPC.
        with TemporaryDirectory() as directory:
            try:
                with chrome(Path(directory) / "probe") as browser:
                    browser.call("Browser.getVersion")
            except BrowserError as error:
                if "Operation not permitted" in str(error):
                    raise unittest.SkipTest("Chrome startup IPC is blocked by the execution sandbox.") from error
                raise

    def print_row(self, row):
        html = sheet_html(DEFAULT_TEMPLATE.read_text(encoding="utf-8"), DEFAULT_TEMPLATE,
                          row, DEFAULT_ASSETS, 3, DEFAULT_REVISION, DEFAULT_DATE)
        with TemporaryDirectory() as directory:
            path = Path(directory)
            return print_document(html, path / "sheet.pdf", path / "work")

    def test_one_page_without_overflow(self):
        row = read_products(ROOT / "data/quillmere-products.xlsx")[0]
        result = self.print_row(row)
        self.assertEqual(result.pages, 1)
        self.assertGreater(result.checked, 10)
        self.assertEqual(result.overflow + result.broken + result.fonts, [])

    def test_absurd_description_overflows_the_real_layout(self):
        row = read_products(ROOT / "data/quillmere-products.csv")[0]
        long_row = replace(row, cells={**row.cells, "description": "Far too much text about this fixture. " * 80})
        result = self.print_row(long_row)
        self.assertTrue(any(box["field"] == "description" and box["height"] > 0 for box in result.overflow))

    def test_fixture_row_passes_cell_checks_but_overflows(self):
        row = read_products(ROOT / "tests/fixtures/bad-products.csv")[2]
        result = self.print_row(row)
        self.assertTrue(any(box["field"] == "description" for box in result.overflow))
