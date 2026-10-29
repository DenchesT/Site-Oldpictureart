# -*- coding: utf-8 -*-
"""Оффлайн-проверки улучшений. Запуск: python -m unittest tests/test_quality_update.py

Для прямого запуска (если tests/ не пакет): python tests/test_quality_update.py
"""

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import tempfile
import unittest
from unittest.mock import patch

from sitebuild import indexnow, links, safety
import apply_build_site_refactor as refactoring
import apply_telegram_fix as telegram_fix


class SafeLinksTests(unittest.TestCase):
    def test_external_link_schemes(self):
        for url in ('javascript:alert(1)', 'data:text/html,<h1>x</h1>',
                    '//evil.example/x', 'file:///etc/passwd',
                    'https://site.example/\n" onmouseover="alert(1)'):
            with self.subTest(url=url):
                self.assertEqual(links.ext_link('<b>caption</b>', url),
                                 '&lt;b&gt;caption&lt;/b&gt;')
        self.assertIn('href="https://museum.example/"',
                      links.ext_link('Музей', 'https://museum.example/'))

    def test_source_filter_deduplication(self):
        items = links.source_items(
            [{'text': 'Каталог', 'url': 'https://art.example/p?utm_source=vk&n=1'},
             {'text': 'Ловушка', 'url': 'javascript:alert(1)'}],
            ['https://art.example/p?n=1', 'https://two.example/', 'data:text/plain,hello'])
        self.assertEqual(items, [('Каталог', 'https://art.example/p?n=1'),
                                 ('https://two.example/', 'https://two.example/')])
        block = links.source_block([('bad', 'javascript:alert(1)'), ('ok', 'https://ok.example/')])
        self.assertIn('<h3>Источник</h3>', block)
        self.assertNotIn('javascript:', block)
        self.assertEqual(links.source_block(None), "")

    def test_link_for_compatibility(self):
        items = [{'text': 'Выставка "Сокровищница графики"', 'url': 'https://x.example'}]
        self.assertEqual(links.link_for('Сокровищница графики', items), 0)
        self.assertIsNone(links.link_for('Сокровищница графики', items, used={0}))


class IndexNowTests(unittest.TestCase):
    def test_all_batches_and_endpoints(self):
        urls = [f'https://oldpictureart.ru/p-{i}.html' for i in range(indexnow.MAX_URLS + 23)]
        requests = []

        def post(endpoint, body):
            requests.append((endpoint, json.loads(body)))
            return 200

        self.assertTrue(indexnow.submit(urls, endpoints=('https://a.example', 'https://b.example'),
                                        post=post, log=lambda _: None))
        self.assertEqual(len(requests), 4)
        for endpoint in ('https://a.example', 'https://b.example'):
            sent = [url for ep, body in requests if ep == endpoint for url in body['urlList']]
            self.assertEqual(sent, urls)

    def test_partial_endpoint_failure_is_failure(self):
        called = []

        def post(url, body):
            called.append(url)
            return 429 if url.endswith('two') else 200

        self.assertFalse(indexnow.submit(['https://oldpictureart.ru/'],
                                         endpoints=('https://one', 'https://two'),
                                         post=post, log=lambda _: None))
        self.assertEqual(called, ['https://one', 'https://two'])

    def test_pending_atomic_and_sitemap(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'pending.json'
            indexnow.save_pending(['https://example.org/'], path)
            self.assertEqual(indexnow.load_pending(path), ['https://example.org/'])
            self.assertFalse(list(Path(folder).glob('*.tmp')))
            indexnow.save_pending([], path)
            self.assertFalse(path.exists())
            (Path(folder) / 'sitemap.xml').write_text(
                '<urlset><url><loc>https://example.org/?a=1&amp;b=2</loc></url></urlset>',
                encoding='utf-8')
            self.assertIn('https://example.org/?a=1&b=2', indexnow.sitemap_urls(folder))


class PublicationSafetyTests(unittest.TestCase):
    def test_private_files_blocked(self):
        for name in ('.env', '.env.production', '.npmrc', '.pypirc', '.netrc',
                     '.ssh/id_rsa', '.aws/credentials', 'credentials.json',
                     'secrets.json', 'private.p12', 'auth.sqlite3',
                     'docs/image.jpg.zip', 'node_modules/a.js', 'output/x.html',
                     '../outside', '/tmp/private', 'docs//x.html'):
            with self.subTest(name=name):
                self.assertFalse(safety.publishable(name))
        for name in ('docs/index.html', 'docs/.nojekyll',
                     'sitebuild/text.py', '.github/workflows/tests.yml'):
            with self.subTest(name=name):
                self.assertTrue(safety.publishable(name))

    def test_atomic_json_rejects_symlink(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'meta.json'
            target = Path(folder) / 'target.json'
            target.write_text('{"old": true}', encoding='utf-8')
            p.symlink_to(target)
            with self.assertRaises(ValueError):
                safety.atomic_json(p, {"test": 1})
            self.assertEqual(target.read_text(), '{"old": true}')

    def test_atomic_json_keeps_old_on_failed_replace(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / 'meta.json'
            safety.atomic_json(p, [1], backup=False)
            real_replace = safety.os.replace

            def broken(src, dst):
                if Path(dst) == p:
                    raise OSError('injected failure')
                return real_replace(src, dst)

            with patch.object(safety.os, 'replace', side_effect=broken):
                with self.assertRaises(OSError):
                    safety.atomic_json(p, [2], backup=False)
            self.assertEqual(json.loads(p.read_text()), [1])




class TelegramFixTests(unittest.TestCase):
    def test_missing_mime_does_not_crash(self):
        source = "def download_images(group):\n" + telegram_fix.OLD + "\n    return docs\n"
        changed = telegram_fix.refactor(source)
        ns = {}
        exec(changed, ns)
        class Document:
            mime_type = None
        class Message:
            document = Document()
        self.assertEqual(ns["download_images"]([Message()]), [])
        self.assertEqual(telegram_fix.refactor(changed), changed)


class MainRefactorTests(unittest.TestCase):
    def test_refactoring_uses_single_comment_reader(self):
        original = (
            'async def main():\n'
            '    try:\n'
            '        if True:\n'
            + refactoring._OLD_POST + '\n'
            + refactoring._OLD_VISIT
            + '        await visit_comments(vm)\n'
            '    finally:\n'
            '        pass\n'
        )
        changed = refactoring.refactor(original)
        self.assertEqual(changed.count('async def _image_comments('), 1)
        self.assertNotIn('async def visit_comments(', changed)
        self.assertIn('await _image_comments(client, mm)', changed)
        self.assertIn('await _image_comments(client, vm)', changed)
        self.assertEqual(refactoring.refactor(changed), changed)
        with self.assertRaises(ValueError):
            refactoring.refactor('async def main():\n    pass\n')

if __name__ == '__main__':
    unittest.main(verbosity=2)
