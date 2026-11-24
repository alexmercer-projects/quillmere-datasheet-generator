"""An escaping template renderer and the print sheet view model."""

from dataclasses import dataclass
from html import escape
from pathlib import Path
import re

from .data import ROOT
from .validate import FIELDS, FINISHES, image_path, parse_number, parse_temperature

TOKEN = re.compile(r"{{\s*(#each\s+[\w.]+|/each|[\w.]+)\s*}}", re.ASCII)
MARK = (
    '<svg viewBox="0 0 40 40" aria-hidden="true"><rect width="40" height="40" rx="8"/>'
    '<path d="M10 26h20M13 21a7 7 0 0 1 14 0M20 7v4m-9 2 3 3m15-3-3 3"/></svg>'
)


@dataclass(frozen=True)
class Markup:
    """Internal HTML, constructed by the renderer from validated data."""

    value: str


@dataclass(frozen=True)
class Field:
    name: str


@dataclass(frozen=True)
class Loop:
    name: str
    body: list


def compile_template(source):
    nodes = []
    stack = [nodes]
    end = 0
    for token in TOKEN.finditer(source):
        stack[-1].append(source[end:token.start()])
        name = token[1]
        if name.startswith("#each"):
            loop = Loop(name.split()[1], [])
            stack[-1].append(loop)
            stack.append(loop.body)
        elif name == "/each":
            if len(stack) == 1:
                raise ValueError("Unexpected {{/each}}.")
            stack.pop()
        else:
            stack[-1].append(Field(name))
        end = token.end()
    if len(stack) != 1:
        raise ValueError("Unclosed {{#each}} block.")
    nodes.append(source[end:])
    return nodes


def lookup(scopes, name):
    if name == ".":
        return scopes[-1]
    parts = name.removeprefix("this.").split(".")
    if name == "this":
        return scopes[-1]
    candidates = scopes[-1:] if name.startswith("this.") else reversed(scopes)
    for scope in candidates:
        if isinstance(scope, dict) and parts[0] in scope:
            value = scope
            for part in parts:
                if not isinstance(value, dict) or part not in value:
                    raise ValueError(f"Unknown template field {name!r}.")
                value = value[part]
            return value
    raise ValueError(f"Unknown template field {name!r}.")


def render_nodes(nodes, scopes):
    for node in nodes:
        if isinstance(node, str):
            yield node
        elif isinstance(node, Field):
            value = lookup(scopes, node.name)
            yield value.value if isinstance(value, Markup) else escape(str(value), quote=True)
        else:
            items = lookup(scopes, node.name)
            if not isinstance(items, (list, tuple)):
                raise ValueError(f"Template loop {node.name!r} requires a list.")
            for item in items:
                yield from render_nodes(node.body, [*scopes, item])


def render(source, context):
    return "".join(render_nodes(compile_template(source), [context]))


def number_text(number):
    return format(number.normalize(), "f")


def dimension_svg(width, height, depth):
    """Draw the dimensioned bounding envelopes at a common scale."""
    scale = min(92 / float(max(width, depth)), 70 / float(height))
    w, h, d = (float(value) * scale for value in (width, height, depth))
    x_front, x_side = 107, 232
    floor = 97

    def mm(value):
        return f"{number_text(value)} mm"

    def inches(value):
        return f'{float(value) / 25.4:.2f} in'

    views = []
    for x, extent, measure, label in (
        (x_front, w, width, "FRONT"), (x_side, d, depth, "SIDE"),
    ):
        left, right = x - extent / 2, x + extent / 2
        views.append(f"""
          <rect class="envelope" x="{left:.2f}" y="{floor-h:.2f}" width="{extent:.2f}" height="{h:.2f}"/>
          <path class="guide" d="M{x} {floor-h-5:.2f}V{floor+4} M{left:.2f} {floor+2}v16 M{right:.2f} {floor+2}v16
            M{left:.2f} {floor+14}H{right:.2f} M{left-2:.2f} {floor+16}l4 -4 M{right-2:.2f} {floor+16}l4 -4"/>
          <text x="{x}" y="15">{label}</text><text class="reading" x="{x}" y="125">{mm(measure)}</text>
          <text x="{x}" y="138">{inches(measure)}</text>""")
    middle = floor - h / 2
    return Markup(f"""
    <svg class="dimension" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 292 147" role="img"
      aria-label="Overall dimensions {mm(width)} wide, {mm(height)} high, and {mm(depth)} deep">
      <path class="guide" d="M59 {floor-h:.2f}h12 M59 {floor}h12 M63 {floor-h:.2f}V{floor}
        M61 {floor-h+2:.2f}l4 -4 M61 {floor+2}l4 -4"/>
      <text class="reading height" x="53" y="{middle-1:.2f}">{mm(height)}</text>
      <text class="height" x="53" y="{middle+12:.2f}">{inches(height)}</text>
      {"".join(views)}
    </svg>""")


def sheet_context(row, assets, page, revision, date):
    cells = row.cells
    numbers = {
        key: parse_number(cells[key], rule.unit)
        for key, rule in FIELDS.items() if rule.bounds
    }
    display = {key: number_text(value) for key, value in numbers.items()}
    low, high = map(number_text, parse_temperature(cells["operating_temp_c"]))
    cct = [item.strip() for item in cells["cct_k"].split("/")]
    finishes = []
    for name in cells["finishes"].split("|"):
        name = name.strip()
        code, color = FINISHES[name]
        finishes.append({"name": name, "code": code, "color": color})

    def entries(heading, values):
        return {"heading": heading, "items": [{"label": k, "value": v} for k, v in values]}

    w, h, d = (numbers[key] for key in ("width_mm", "height_mm", "depth_mm"))
    return {
        **cells,
        **display,
        "brand_mark": Markup(MARK),
        "image_uri": image_path(cells["image"], assets).resolve().as_uri(),
        "page": f"{page:02}",
        "revision": revision,
        "date": date,
        "figures": [
            {"value": f"{numbers['lumens']:,.0f}", "label": "Lumens", "unit": "lm"},
            {"value": display["watts"], "label": "Input power", "unit": "W"},
            {"value": display["efficacy"], "label": "Efficacy", "unit": "lm/W"},
            {"value": display["cri"], "label": "Color rendering", "unit": "CRI"},
            {"value": display["beam_angle_deg"] + "°", "label": "Beam angle", "unit": ""},
        ],
        "spec_groups": [
            entries("Optical", [("CCT options", " / ".join(cct) + " K"),
                               ("Delivered flux", display["lumens"] + " lm")]),
            entries("Electrical", [("Supply", cells["voltage"]),
                                   ("Power", display["watts"] + " W")]),
            entries("Physical", [("Housing", cells["housing_material"]),
                                 ("Weight", display["weight_kg"] + " kg"),
                                 ("Mounting", cells["mounting"])]),
            entries("Environmental", [("Exposure", cells["ip_rating"] + " (example rating)"),
                                      ("Impact", cells["ik_rating"] + " (example rating)"),
                                      ("Operating", f"{low} to {high} °C"),
                                      ("Warranty", display["warranty_years"] + " years (example)"),
                                      ("Listings", cells["certifications_placeholder"])]),
        ],
        "finish_options": finishes,
        "dimension_drawing": dimension_svg(w, h, d),
        "ordering_code": f"{row.sku}-[CCT]-[FINISH]",
        "ordering_example": f"{row.sku}-{cct[0]}-{finishes[0]['code']}",
        "cct_options": " / ".join(cct),
        "accessory_text": cells.get("accessories", "").replace("|", "·") or "None listed",
        "note_text": cells.get("notes", "") or "None listed",
    }


def sheet_html(source, template_path, row, assets, page, revision, date):
    template_path = Path(template_path).resolve()
    context = sheet_context(row, assets, page, revision, date)
    context.update(
        template_base=template_path.parent.as_uri() + "/",
        fonts_base=(ROOT / "docs/fonts").as_uri() + "/",
    )
    return render(source, context)
