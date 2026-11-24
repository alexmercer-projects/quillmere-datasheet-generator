# Quillmere validation report

Concept demo. The fixture data and ratings are examples.

Input file: bad-products.csv

4 rows checked, 1 sheets written, 3 catalog pages, 17 errors, 1 warnings.

| Severity | Row | SKU | Field | Rule | Finding |
| --- | --- | --- | --- | --- | --- |
| error | 2 | QL-WAL-12 | name | required | A value is required. |
| error | 2 | QL-WAL-12 | tagline | length | 104 characters exceeds the 70-character limit. |
| error | 2 | QL-WAL-12 | lumens | number | Enter a finite number without separators. |
| error | 2 | QL-WAL-12 | cri | range | Whole number from 0 to 100. |
| error | 2 | QL-WAL-12 | width\_mm | unit | Expected mm; got in. |
| error | 2 | QL-WAL-12 | weight\_kg | unit | Expected kg; got lbs. |
| error | 2 | QL-WAL-12 | sku | duplicate | The SKU appears on more than one row. |
| error | 2 | QL-WAL-12 | operating\_temp\_c | unit | Operating temperatures must use Celsius (°C). |
| error | 2 | QL-WAL-12 | image | image | Fixture image 'missing.svg' was not found in the image directory. |
| error | 2 | QL-WAL-12 | finishes | finish | Unknown finish 'Copper'. |
| warning | 2 | QL-WAL-12 | accessories | optional | No accessories listed. The sheet will show 'None listed'. |
| error | 3 | QL-WAL-12 | ip\_rating | length | 10 characters exceeds the 4-character limit. |
| error | 3 | QL-WAL-12 | ip\_rating | format | Example code in the form IP65. |
| error | 3 | QL-WAL-12 | notes | length | 106 characters exceeds the 105-character limit. |
| error | 3 | QL-WAL-12 | sku | duplicate | The SKU appears on more than one row. |
| error | 3 | QL-WAL-12 | efficacy | efficacy | Lumens ÷ watts is 80.00 lm/W. Allowed difference is 2%. |
| error | 3 | QL-WAL-12 | cct\_k | format | Whole Kelvin values, 1800 through 6500, split with /. Each value must be unique. |
| error | 4 | QL-BOL-ERROR | description | overflow | Text exceeds the print box by 0 px wide, 72 px tall. |
