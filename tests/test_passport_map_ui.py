# -*- coding: utf-8 -*-
"""Lightweight regression checks for Art Passport map, overview, and calendar."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / 'docs' / 'passport.js').read_text(encoding='utf-8')
CSS = (ROOT / 'docs' / 'passport.css').read_text(encoding='utf-8')
PY = (ROOT / 'sitebuild' / 'passport.py').read_text(encoding='utf-8')

class PassportMapUITest(unittest.TestCase):
    def test_wheel_zoom_is_on(self):
        self.assertIn('scrollWheelZoom:true', JS)
        self.assertNotIn('scrollWheelZoom:false', JS)

    def test_shared_map_layer_setup_is_preserved(self):
        self.assertIn('OPA_MAP.attach(map,mapEl)', JS)
        self.assertIn('MAP_LAYERS_JS', PY)

    def test_overview_action_buttons_have_equal_grid_rows(self):
        self.assertIn("passport-shortcuts passport-overview-actions", JS)
        self.assertIn('.passport-overview-actions{display:grid;', CSS)
        self.assertIn('grid-auto-rows:1fr;', CSS)
        self.assertIn('.passport-overview-actions>button', CSS)

    def test_calendar_in_scrollable_dialog(self):
        self.assertIn('function openCalendar()', JS)
        self.assertIn("wrap.closest('.passport-modal')", JS)
        self.assertIn('dialog.scrollTop+=calendar.bottom-bottom', JS)
        self.assertIn('.passport-page .passport-date-popup{position:relative;', CSS)
        self.assertIn('overflow-y:auto;', CSS)

    def test_updated_asset_urls(self):
        self.assertIn('passport.css?v=20261109-2', PY)
        self.assertIn('passport.js?v=20261109-2', PY)

if __name__ == '__main__':
    unittest.main()
