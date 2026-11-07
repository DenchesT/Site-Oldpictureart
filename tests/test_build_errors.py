"""Build failures must prevent a successful publication, even in offline mode."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import rebuild_pages
from sitebuild import museums


class BuildErrorTests(unittest.TestCase):
    def test_failed_generator_stops_offline_build(self):
        for failed in ('generate_quiz.py', 'generate_timeline.py', 'generate_map.py'):
            with self.subTest(script=failed), tempfile.TemporaryDirectory() as folder:
                facade = MagicMock()
                facade.OUTPUT_DIR = folder
                facade.IMAGES_DIR = os.path.join(folder, 'images')
                facade.load_json.return_value = [{'filename': 'work.html'}]
                for name in ('render_post_page', 'render_index', 'render_404',
                             'render_privacy', 'render_auth_page'):
                    getattr(facade, name).return_value = ''

                def generate(command, **kwargs):
                    if command[1] == failed:
                        raise subprocess.CalledProcessError(1, command)

                with patch.object(rebuild_pages, 'bs', facade), \
                     patch.object(sys, 'argv', ['rebuild_pages.py', '--offline']), \
                     patch.object(rebuild_pages.subprocess, 'run', side_effect=generate):
                    with self.assertRaises(subprocess.CalledProcessError):
                        rebuild_pages.main()
                facade.generate_museum_pages.assert_not_called()
                facade.generate_afisha.assert_not_called()

    def test_map_failure_propagates_to_telegram_builder(self):
        with patch.object(museums.subprocess, 'run',
                          side_effect=subprocess.CalledProcessError(1, ['generate_map.py'])):
            with self.assertRaises(subprocess.CalledProcessError):
                museums.generate_museums_page([])


if __name__ == '__main__':
    unittest.main(verbosity=2)
