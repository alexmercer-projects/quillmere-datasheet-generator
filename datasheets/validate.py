"""Validate spreadsheet values and describe their rules."""

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
import re

FINISHES = {
    "Graphite": ("GR", "#343839"),
    "Bronze": ("BZ", "#77604e"),
    "Sand": ("SA", "#c7b8a1"),
    "Chalk": ("CH", "#ece9df"),
    "Olive": ("OL", "#656a53"),
}


@dataclass(frozen=True)
class Rule:
    guidance: str
    limit: int | None = None
    bounds: tuple[int, int] | None = None
    whole: bool = False
    unit: str = ""
    required: bool = True
    pattern: str = ""


FIELDS = {
    "sku": Rule("Unique uppercase code, using letters, numbers and internal hyphens.", 24,
                pattern=r"[A-Z0-9]+(?:-[A-Z0-9]+)*"),
    "name": Rule("Product name, up to 48 characters.", 48),
    "family": Rule("Product family, up to 32 characters.", 32),
    "tagline": Rule("One short line, up to 70 characters.", 70),
    "description": Rule("Two or three sentences, up to 420 characters.", 420),
    "lumens": Rule("Whole number from 1 to 100,000.", bounds=(1, 100000), whole=True, unit="lm"),
    "watts": Rule("Number from 0.1 to 1,000.", bounds=(0.1, 1000), unit="W"),
    "efficacy": Rule("Number from 1 to 300, within 2% of lumens divided by watts.",
                     bounds=(1, 300), unit="lm/W"),
    "cct_k": Rule("Whole Kelvin values, 1800 through 6500, split with /.", 30),
    "cri": Rule("Whole number from 0 to 100.", bounds=(0, 100), whole=True),
    "beam_angle_deg": Rule("Number from 1 to 180.", bounds=(1, 180), unit="°"),
    "voltage": Rule("Example supply type, such as 120 V AC or 24 V DC.", 26),
    "ip_rating": Rule("Example code in the form IP65.", 4, pattern=r"IP[0-6X][0-9X]"),
    "ik_rating": Rule("Example code in the form IK08.", 4, pattern=r"IK(?:0[0-9]|10)"),
    "housing_material": Rule("Housing material, up to 38 characters.", 38),
    "finishes": Rule("Pipe-separated names. " + ", ".join(FINISHES) + ".", 65),
    "width_mm": Rule("Number from 1 to 5,000. Millimetres.", bounds=(1, 5000), unit="mm"),
    "height_mm": Rule("Number from 1 to 5,000. Millimetres.", bounds=(1, 5000), unit="mm"),
    "depth_mm": Rule("Number from 1 to 5,000. Millimetres.", bounds=(1, 5000), unit="mm"),
    "weight_kg": Rule("Number from 0.01 to 500. Kilograms.", bounds=(0.01, 500), unit="kg"),
    "mounting": Rule("Mounting description, up to 48 characters.", 48),
    "operating_temp_c": Rule("Two Celsius temperatures with an ascending range, e.g. -25 to 45.", 32),
    "warranty_years": Rule("Whole number from 0 to 20.", bounds=(0, 20), whole=True, unit="years"),
    "certifications_placeholder": Rule("Use the literal Listing: placeholder.", 40,
                                        pattern=r"Listing: placeholder"),
    "image": Rule("Local filename of an SVG, PNG, JPG, JPEG or WebP in assets/products.", 90),
    "accessories": Rule("Accessory text, up to 100 characters. Optional.", 100, required=False),
    "notes": Rule("Installation notes, up to 105 characters. Optional.", 105, required=False),
}

NUMBER = r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)"
# Parse a unit suffix separately so the report can name the supplied unit.
MEASUREMENT = re.compile(rf"({NUMBER})\s*([a-zA-Z°%/\"]+)?")
TEMPERATURE = re.compile(rf"({NUMBER})\s*(?:°?\s*([CFK]))?\s+to\s+"
                         rf"({NUMBER})\s*(?:°?\s*([CFK]))?", re.IGNORECASE)


class InvalidValue(ValueError):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def parse_number(value, unit=""):
    match = MEASUREMENT.fullmatch(value.strip())
    if not match:
        raise InvalidValue("number", "Enter a finite number without separators.")
    number, supplied = match.groups()
    if supplied and supplied.casefold() != unit.casefold():
        expected = unit or "no unit suffix"
        raise InvalidValue("unit", f"Expected {expected}; got {supplied}.")
    return Decimal(number)


def parse_temperature(value):
    match = TEMPERATURE.fullmatch(value)
    if not match:
        raise InvalidValue("temperature", "Enter a Celsius range, for example -25 to 45.")
    start, start_unit, end, end_unit = match.groups()
    if any(unit and unit.upper() != "C" for unit in (start_unit, end_unit)):
        raise InvalidValue("unit", "Operating temperatures must use Celsius (°C).")
    low, high = Decimal(start), Decimal(end)
    if not -100 <= low < high <= 100:
        raise InvalidValue("range", "Use ascending temperatures between -100 and 100 °C.")
    return low, high


def image_path(value, assets):
    path = Path(value)
    if (path.name != value or "\\" in value
            or path.suffix.lower() not in {".svg", ".png", ".jpg", ".jpeg", ".webp"}):
        raise InvalidValue("image", "Use a local fixture image filename.")
    candidate = assets / path
    if not candidate.resolve().is_relative_to(assets.resolve()) or not candidate.is_file():
        raise InvalidValue("image", f"Fixture image {value!r} was not found in the image directory.")
    return candidate


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    message: str
    field: str = ""
    row: int | None = None
    sku: str = ""


def validate_row(row, assets, sku_counts):
    issues = []
    numbers = {}

    def add(field, code, message, severity="error"):
        issues.append(Issue(severity, code, message, field, row.number, row.sku))

    for field, rule in FIELDS.items():
        value = row.cells.get(field, "")
        if not value:
            if rule.required:
                add(field, "required", "A value is required.")
            continue
        if rule.limit and len(value) > rule.limit:
            add(field, "length", f"{len(value)} characters exceeds the {rule.limit}-character limit.")
        if rule.pattern and not re.fullmatch(rule.pattern, value):
            add(field, "format", rule.guidance)
        if rule.bounds:
            try:
                number = parse_number(value, rule.unit)
                low, high = map(lambda bound: Decimal(str(bound)), rule.bounds)
                if not low <= number <= high or (rule.whole and number % 1):
                    raise InvalidValue("range", rule.guidance)
                numbers[field] = number
            except InvalidValue as error:
                add(field, error.code, str(error))

    if row.sku and sku_counts[row.sku.casefold()] > 1:
        add("sku", "duplicate", "The SKU appears on more than one row.")
    if numbers.keys() >= {"lumens", "watts", "efficacy"}:
        expected = numbers["lumens"] / numbers["watts"]
        if abs(numbers["efficacy"] - expected) > expected * Decimal("0.02"):
            add("efficacy", "efficacy", f"Lumens ÷ watts is {expected:.2f} lm/W. Allowed difference is 2%.")

    cells = row.cells
    for field, parser in (("operating_temp_c", parse_temperature),
                          ("image", lambda value: image_path(value, assets))):
        if value := cells.get(field):
            try:
                parser(value)
            except InvalidValue as error:
                add(field, error.code, str(error))

    if cct := cells.get("cct_k"):
        options = [value.strip() for value in cct.split("/")]
        if any(not re.fullmatch(r"[0-9]{4}", value) or not 1800 <= int(value) <= 6500
               for value in options) or len(set(options)) != len(options):
            add("cct_k", "format", FIELDS["cct_k"].guidance + " Each value must be unique.")

    if finishes := cells.get("finishes"):
        names = [value.strip() for value in finishes.split("|")]
        for name in dict.fromkeys(names):
            if name not in FINISHES:
                add("finishes", "finish", f"Unknown finish {name!r}.")
        if len(set(names)) != len(names):
            add("finishes", "duplicate", "List each finish once.")
    if not cells.get("accessories"):
        add("accessories", "optional", "No accessories listed. The sheet will show 'None listed'.", "warning")
    return issues


def validate_products(rows, assets, only=None):
    counts = Counter(row.sku.casefold() for row in rows if row.sku)
    return [
        issue
        for row in rows if only is None or row.sku == only
        for issue in validate_row(row, assets, counts)
    ]
