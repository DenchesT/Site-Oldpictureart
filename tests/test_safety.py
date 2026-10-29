"""CI regression tests for automatic commits and absence of local test runs."""
import ast
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("safety_under_test", ROOT / "sitebuild/safety.py")
safety = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safety)


class AutoPublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        old = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, old)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.root / "docs").mkdir()
        (self.root / "docs/index.html").write_text("old")
        (self.root / "build_site.py").write_text("old")
        (self.root / ".gitignore").write_text("ignored.txt\n.env\nnode_modules/\n")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True).stdout

    def publish(self, fail=False):
        real = safety.git
        self.calls = []
        def run(*args, **kwargs):
            self.calls.append(args)
            if args == ("push",):
                if fail: raise RuntimeError("simulated push failure")
                return b""
            return real(*args, **kwargs)
        with patch.object(safety, "git", side_effect=run):
            return safety.publish_generated(self.root)

    def test_source_and_content_committed_together(self):
        (self.root / "build_site.py").write_text("new code")
        (self.root / "docs/index.html").write_text("new page")
        self.assertEqual(self.publish(), ["build_site.py", "docs/index.html"])
        self.assertEqual(self.git("diff", "HEAD", "--name-only"), b"")
        self.assertIn(("push",), self.calls)

    def test_staged_source_is_accepted(self):
        (self.root / "build_site.py").write_text("staged source")
        self.git("add", "build_site.py")
        self.assertEqual(self.publish(), ["build_site.py"])

    def test_new_source_and_workflow_are_included(self):
        (self.root / "helper.py").write_text("# new source")
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / ".github/workflows/tests.yml").write_text("name: tests")
        self.assertEqual(self.publish(), [".github/workflows/tests.yml", "helper.py"])

    def test_sensitive_and_temp_files_excluded(self):
        for name in (".env", ".env.local", "a.session", "data.json.bak", "private.pem", "archive.zip"):
            (self.root / name).write_text("not for publication")
        (self.root / "build_site.py").write_text("new")
        self.assertEqual(self.publish(), ["build_site.py"])
        tracked = self.git("ls-files").decode().splitlines()
        self.assertNotIn("a.session", tracked)
        self.assertNotIn(".env.local", tracked)

    def test_gitignore_honored(self):
        (self.root / "ignored.txt").write_text("ignored")
        self.assertIsNone(self.publish())
        self.assertNotIn("ignored.txt", self.git("ls-files").decode())

    def test_staged_secret_is_refused(self):
        (self.root / ".env").write_text("SECRET=x")
        self.git("add", "-f", ".env")
        with self.assertRaises(RuntimeError): self.publish()
        self.assertNotIn(("push",), self.calls)

    def test_deleted_file_committed(self):
        (self.root / "docs/index.html").unlink()
        self.assertEqual(self.publish(), ["docs/index.html"])
        self.assertEqual(self.git("ls-tree", "--name-only", "HEAD", "docs/index.html"), b"")

    def test_filename_with_space(self):
        (self.root / "new helper.py").write_text("pass")
        self.assertEqual(self.publish(), ["new helper.py"])

    def test_push_retry_without_diff(self):
        self.assertIsNone(self.publish())
        self.assertIn(("push",), self.calls)

    def test_push_error_propagates(self):
        with self.assertRaises(RuntimeError): self.publish(fail=True)


class StorageAndBuildTests(unittest.TestCase):
    def test_atomic_json_and_backup(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "data.json"
            safety.atomic_json(p, {"title": "Картина"})
            safety.atomic_json(p, {"title": "Музей"})
            self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"title": "Музей"})
            self.assertEqual(json.loads(p.with_suffix(".json.bak").read_text(encoding="utf-8")), {"title": "Картина"})
            with self.assertRaises(TypeError): safety.atomic_json(p, object())
            self.assertEqual(json.loads(p.read_text(encoding="utf-8")), {"title": "Музей"})

    def test_replace_failure_preserves_data(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder) / "data.json"
            safety.atomic_json(p, [1])
            real = os.replace
            def fail(src, dst):
                if Path(dst) == p: raise OSError("injected")
                return real(src, dst)
            with patch.object(safety.os, "replace", side_effect=fail):
                with self.assertRaises(OSError): safety.atomic_json(p, [2])
            self.assertEqual(json.loads(p.read_text()), [1])

    def test_no_test_commands_in_builder(self):
        source = (ROOT / "build_site.py").read_text(encoding="utf-8")
        for text in ("tests/run.js", "tests/test_safety.py", "npm ci", "playwright install"):
            self.assertNotIn(text, source)

    def test_push_function_only_delegates(self):
        tree = ast.parse((ROOT / "build_site.py").read_text(encoding="utf-8"))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "push_to_github")
        publish = Mock(return_value=["build_site.py"])
        ns = {"Path": Path, "__file__": str(ROOT / "build_site.py"),
              "logger": logging.getLogger("test"), "publish_generated": publish}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "build_site.py", "exec"), ns)
        with patch.object(Path, "cwd", return_value=ROOT), patch.object(subprocess, "run") as run:
            self.assertEqual(ns["push_to_github"](), ["build_site.py"])
        run.assert_not_called()
        publish.assert_called_once_with(ROOT)

    def test_safety_exports(self):
        for name in ("atomic_json", "publishable", "git", "publish_generated", "GENERATED_FILES"):
            self.assertIn(name, safety.__all__)

    def test_newline_arguments(self):
        tree = ast.parse((ROOT / "build_site.py").read_text(encoding="utf-8"))
        values = [k.value.value for node in ast.walk(tree) if isinstance(node, ast.Call)
                  for k in node.keywords if k.arg == "newline" and isinstance(k.value, ast.Constant)]
        self.assertTrue(values)
        self.assertTrue(all(v == "\n" for v in values))


if __name__ == "__main__":
    unittest.main(verbosity=2)
