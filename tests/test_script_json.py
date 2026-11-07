"""Data containing HTML must remain data inside generated script elements."""
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from site_common import script_json
from sitebuild.html import artwork_jsonld, jsonld_script
from sitebuild.posts import render_index

PAYLOAD = '</ScRiPt><script id="injected">alert(1)</script><!--<&\u2028\u2029'


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            self.scripts.append(dict(attrs))


class ScriptJsonTests(unittest.TestCase):
    def test_roundtrip_and_no_html_tokens(self):
        data = {'title': PAYLOAD, 'русский': 'Моне & Сислей'}
        for ascii_only in (True, False):
            encoded = script_json(data, ensure_ascii=ascii_only)
            self.assertEqual(json.loads(encoded), data)
            self.assertNotIn('<', encoded)
            self.assertNotIn('\u2028', encoded)
            self.assertNotIn('\u2029', encoded)

    def test_jsonld_cannot_create_second_script(self):
        for markup in (jsonld_script({'name': PAYLOAD}), artwork_jsonld({'title': PAYLOAD})):
            parsed = Scripts()
            parsed.feed(markup)
            self.assertEqual(parsed.scripts, [{'type': 'application/ld+json'}])
            self.assertEqual(json.loads(markup.split('>', 1)[1].rsplit('<', 1)[0])['name'], PAYLOAD)

    def test_gallery_data_cannot_escape_script(self):
        posts = json.loads(Path('posts_meta.json').read_text('utf-8'))
        posts[0]['title'] = PAYLOAD
        with patch('sitebuild.posts.load_afisha', return_value=([], [])):
            markup = render_index(posts, visits=[])
        parsed = Scripts()
        parsed.feed(markup)
        self.assertFalse(any(s.get('id') == 'injected' for s in parsed.scripts))
        self.assertIn('\\u003c/ScRiPt', markup)


if __name__ == '__main__':
    unittest.main(verbosity=2)
