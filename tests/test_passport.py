# -*- coding: utf-8 -*-
"""Offline regression checks for Old Picture Art personal passport."""
import unittest
from unittest.mock import patch

from sitebuild.passport import passport_catalog, render_passport_page


class PassportTests(unittest.TestCase):
    def setUp(self):
        self.posts = [
            {'id': 101, 'filename': 'work-101.html', 'artist': 'Автор',
             'title': 'Картина', 'museum': 'Музей', 'creation_year': 1892,
             'thumbs': ['images/thumbs/work-101.jpg'], 'images': ['images/work-101.jpg']},
            {'id': 102, 'filename': 'work-102.html', 'artist': 'Автор',
             'title': '</script><script>window.pwned=1</script>',
             'images': ['images/work-102.jpg']},
        ]
        self.visits = []

    def test_catalog_normalizes_ids_and_deduplicates_artists(self):
        with patch('sitebuild.passport.museum_names', return_value=['Музей']):
            data = passport_catalog(self.posts, self.visits)
        self.assertEqual(['101', '102'], [x['id'] for x in data['works']])
        self.assertEqual(['Автор'], [x['name'] for x in data['artists']])
        self.assertEqual(['Музей'], [x['name'] for x in data['museums']])
        self.assertEqual('images/thumbs/work-101.jpg', data['works'][0]['thumb'])

    def test_render_has_privacy_and_safe_catalog(self):
        with patch('sitebuild.passport.museum_names', return_value=['Музей']):
            html = render_passport_page(self.posts, self.visits, exhibitions=[])
        self.assertIn('passport.css', html)
        self.assertIn('passport.js', html)
        self.assertIn('passport-actions.js', html)
        self.assertIn('noindex, nofollow', html)
        self.assertIn('window.OPA_PASSPORT_DATA=', html)
        self.assertNotIn('</script><script>window.pwned', html)
        self.assertIn('Мой арт-паспорт', html)
        self.assertIn('Выставки', html)
        self.assertIn('Коллекции', html)


if __name__ == '__main__':
    unittest.main()
