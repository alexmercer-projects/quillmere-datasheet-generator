import unittest

from datasheets.render import render


class RenderTests(unittest.TestCase):
    def test_fields_and_nested_scopes(self):
        template = "{{title}}{{#each groups}}({{name}} {{#each values}}{{this}}/{{title}} {{/each}}){{/each}}"
        context = {"title": "A", "groups": [{"name": "B", "values": [1, 2]}]}
        self.assertEqual(render(template, context), "A(B 1/A 2/A )")

    def test_html_and_attribute_escaping(self):
        self.assertEqual(
            render('<p title="{{value}}">{{value}}</p>', {"value": '<img src="x">&'}),
            '<p title="&lt;img src=&quot;x&quot;&gt;&amp;">&lt;img src=&quot;x&quot;&gt;&amp;</p>',
        )

    def test_empty_loop_and_dotted_field(self):
        self.assertEqual(render("{{item.name}}{{#each none}}x{{/each}}",
                                {"item": {"name": "Cairn"}, "none": []}), "Cairn")

    def test_bad_templates_fail_clearly(self):
        for template in ("{{missing}}", "{{/each}}", "{{#each values}}", "{{#each text}}x{{/each}}"):
            with self.subTest(template=template), self.assertRaises(ValueError):
                render(template, {"text": "x", "values": []})
