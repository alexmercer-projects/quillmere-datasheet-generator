"""Write machine-readable and human-readable run reports."""

from collections import Counter
import csv
from dataclasses import asdict
import json

MANIFEST_FIELDS = ("sku", "name", "file", "pages", "bytes", "status")


def markdown_value(value):
    text = str(value).replace("\\", "\\\\")
    for char in ("`", "*", "_", "[", "]", "<", ">", "|"):
        text = text.replace(char, "\\" + char if char not in "<>" else {"<": "&lt;", ">": "&gt;"}[char])
    return " ".join(text.splitlines())


def write_reports(directory, source, rows, issues, manifest, catalog):
    counts = Counter(issue.severity for issue in issues)
    summary = {
        "products": len(rows),
        "sheets": sum(bool(item["file"]) for item in manifest),
        "errors": counts["error"],
        "warnings": counts["warning"],
        "catalog_pages": catalog,
    }
    payload = {"source": source.name, "summary": summary, "issues": [asdict(issue) for issue in issues]}
    (directory / "validation-report.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
    )
    lines = [
        "# Quillmere validation report", "",
        "Concept demo. The fixture data and ratings are examples.", "",
        f"Input file: {markdown_value(source.name)}", "",
        f"{summary['products']} rows checked, {summary['sheets']} sheets written, "
        f"{catalog} catalog pages, {summary['errors']} errors, {summary['warnings']} warnings.", "",
    ]
    if issues:
        lines += ["| Severity | Row | SKU | Field | Rule | Finding |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for issue in issues:
            values = (issue.severity, issue.row or "", issue.sku, issue.field, issue.code, issue.message)
            lines.append("| " + " | ".join(map(markdown_value, values)) + " |")
    else:
        lines.append("All rows passed the spreadsheet, text fit, and single-page checks.")
    (directory / "validation-report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    with (directory / "manifest.csv").open("w", encoding="utf-8", newline="") as target:
        writer = csv.DictWriter(target, MANIFEST_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(manifest)
    return summary
