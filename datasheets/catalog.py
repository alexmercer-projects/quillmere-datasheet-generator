"""Create the two introductory pages that precede the individual sheets."""

from math import ceil

from .data import ROOT
from .render import MARK, Markup, render
from .validate import image_path

CONTENTS_CAPACITY = 18


def intro_pages(product_count):
    return 1 + ceil(product_count / CONTENTS_CAPACITY)


INTRO = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Quillmere Lighting Co. / Concept catalog</title>
  <link rel="stylesheet" href="{{css}}">
  <style>
    @font-face {font-family: Schibsted;src:url("{{fonts}}SchibstedGrotesk.woff2");font-weight:100 900}
    @font-face {font-family: JetBrains;src:url("{{fonts}}JetBrainsMono.woff2");font-weight:100 800}
    .cover { break-after: page; background: #243534; color: #fbfaf6; }
    .cover .mast { border-color: #a4a89a; }
    .cover .brand rect { fill: #f0eee4; }
    .cover .brand path { stroke: #794c18; }
    .cover .mast-meta, .cover .mast-meta strong, .cover .overline { color: #f2c989; }
    .cover h1 { font-size: 95px; line-height: .94; margin: 26px 0 20px; }
    .cover-copy { margin: 74px 0 35px; }
    .cover-copy > p:last-child { color: #e5e4d7; font-size: 19px; }
    .cover-plate { height: 540px; position: relative; display: grid; place-items: center; background: #f0eee4; border-radius: 8px; }
    .cover-plate img { width: 82%; height: 460px; object-fit: contain; }
    .cover .folio, .cover footer, .cover .folio span { color: #f2c989; }
    .cover footer { border-color: #a4a89a; }
    .contents:not(:last-child) { break-after: page; }
    .contents .overline { margin-top: 48px; }
    .contents h1 { margin: 9px 0 18px; }
    .contents-list { margin-top: 31px; }
    .contents-row { display: grid; grid-template-columns: 143px 1fr 134px 42px; align-items: center; gap: 11px;
      border-bottom: 1px solid var(--line); padding: 7px 0; font-size: 13px; }
    .contents-row.heading { font: 700 10px var(--mono); border-bottom-color: var(--ink); color: var(--accent); }
    .contents-row span:nth-child(n+3) { font-family: var(--mono); font-size: 10px; }
    .contents-row span:last-child { text-align: right; }
  </style>
</head>
<body>
<main>
  <section class="sheet cover">
    <header class="mast">
      <div class="brand">{{mark}}<div><strong>Quillmere</strong><small>Lighting Co.</small></div></div>
      <div class="mast-meta"><span>Architectural lighting</span><strong>Catalog / Demo</strong></div>
    </header>
    <div class="cover-copy">
      <p class="overline">Outdoor fixtures / Example collection</p>
      <h1>Product catalog</h1>
      <p>{{count}} fixture sheets across {{families}} product families.</p>
    </div>
    <figure class="cover-plate">
      <span class="plate-label">{{sku}} / {{name}}</span>
      <img src="{{image}}" alt="{{name}} fixture illustration">
      <figcaption>Fixture illustration / NTS</figcaption>
    </figure>
    <footer><p>Concept demo - example data, not a real product.</p><p class="folio">Rev {{revision}} · {{date}} · Catalog p. 01</p></footer>
  </section>
  {{#each directory_pages}}
  <section class="sheet contents">
    <header class="mast">
      <div class="brand">{{mark}}<div><strong>Quillmere</strong><small>Lighting Co.</small></div></div>
      <div class="mast-meta"><span>Architectural lighting</span><strong>Catalog / Demo</strong></div>
    </header>
    <p class="overline">Outdoor fixtures / Directory</p>
    <h1>Contents</h1>
    <p>{{count}} fixture sheets in spreadsheet order.</p>
    <div class="contents-list">
      <div class="contents-row heading"><span>Family</span><span>Product</span><span>SKU</span><span>Page</span></div>
      {{#each items}}
      <div class="contents-row"><span>{{family}}</span><strong>{{name}}</strong><span>{{sku}}</span><span>{{page}}</span></div>
      {{/each}}
    </div>
    <footer><p>Concept demo - example data, not a real product.</p><p class="folio">Rev {{revision}} · {{date}} · Catalog p. {{folio}}</p></footer>
  </section>
  {{/each}}
</main>
</body>
</html>"""


def catalog_html(rows, assets, revision, date):
    featured = next((row for row in rows if row.sku == "QL-BOL-42"), rows[0])
    cells = featured.cells
    items = [
        {**row.cells, "page": f"{page:02}"}
        for page, row in enumerate(rows, start=intro_pages(len(rows)) + 1)
    ]
    return render(INTRO, {
        "css": (ROOT / "template/datasheet.css").as_uri(),
        "fonts": (ROOT / "docs/fonts").as_uri() + "/",
        "mark": Markup(MARK),
        "count": len(rows),
        "families": len({row.cells["family"] for row in rows}),
        "image": image_path(cells["image"], assets).resolve().as_uri(),
        "name": cells["name"],
        "sku": featured.sku,
        "revision": revision,
        "date": date,
        "directory_pages": [
            {"folio": f"{page:02}", "items": items[start:start + CONTENTS_CAPACITY]}
            for page, start in enumerate(range(0, len(items), CONTENTS_CAPACITY), start=2)
        ],
    })
