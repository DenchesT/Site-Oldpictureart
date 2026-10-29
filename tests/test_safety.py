"""Regression tests executed by GitHub Actions, not by local build_site.py."""
import ast
import asyncio
import importlib.util
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("opa_safety", ROOT / "sitebuild/safety.py")
safety = importlib.util.module_from_spec(spec)
spec.loader.exec_module(safety)


class AtomicTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.target = Path(self.temp.name) / "data.json"

    def test_unicode_and_backup(self):
        safety.atomic_json(self.target, {"name": "Картина"})
        safety.atomic_json(self.target, {"name": "Музей"})
        self.assertEqual(json.loads(self.target.read_text(encoding="utf-8")), {"name": "Музей"})
        self.assertEqual(json.loads(self.target.with_name("data.json.bak").read_text(encoding="utf-8")), {"name": "Картина"})

    def test_serialization_failure_preserves_original(self):
        safety.atomic_json(self.target, [1])
        with self.assertRaises(TypeError): safety.atomic_json(self.target, object())
        self.assertEqual(json.loads(self.target.read_text()), [1])

    def test_replace_failure_preserves_original(self):
        safety.atomic_json(self.target, [1])
        real_replace = os.replace
        def fail(src, dst):
            if Path(dst) == self.target: raise OSError("injected failure")
            return real_replace(src, dst)
        with patch.object(safety.os, "replace", side_effect=fail):
            with self.assertRaises(OSError): safety.atomic_json(self.target, [2])
        self.assertEqual(json.loads(self.target.read_text()), [1])
        self.assertFalse(list(self.target.parent.glob("*.tmp")))

    def test_corrupt_old_json_is_not_overwritten(self):
        self.target.write_text("broken")
        with self.assertRaises(json.JSONDecodeError): safety.atomic_json(self.target, [2])
        self.assertEqual(self.target.read_text(), "broken")


class PublishTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.old = Path.cwd()
        os.chdir(self.root)
        self.addCleanup(os.chdir, self.old)
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        (self.root / "docs").mkdir()
        (self.root / "docs/index.html").write_text("old")
        (self.root / "source.py").write_text("old")
        self.git("add", ".")
        self.git("commit", "-qm", "initial")

    def git(self, *args):
        return subprocess.run(["git", *args], check=True, capture_output=True).stdout

    def run_publish(self, fail_push=False):
        real = safety.git
        calls = []
        def local(*args, **kwargs):
            calls.append(args)
            if args == ("push",):
                if fail_push: raise subprocess.CalledProcessError(1, ["git", "push"])
                return b""
            return real(*args, **kwargs)
        with patch.object(safety, "git", side_effect=local):
            result = safety.publish_generated(self.root)
        return result, calls

    def test_allowlist(self):
        for name in ("docs/index.html", "posts_meta.json", "docs/images/a.jpg"):
            self.assertTrue(safety.publishable(name))
        for name in (".env", "source.py", "posts_meta.json.bak", "docs/.env", "../docs/x", "docs/a.tmp"):
            self.assertFalse(safety.publishable(name))

    def test_only_generated_files_committed(self):
        (self.root / "docs/index.html").write_text("new")
        (self.root / "private.txt").write_text("not for publication")
        result, calls = self.run_publish()
        self.assertEqual(result, ["docs/index.html"])
        names = self.git("show", "--pretty=", "--name-only", "HEAD").decode().splitlines()
        self.assertEqual(names, ["docs/index.html"])
        self.assertIn(("push",), calls)

    def test_dirty_source_refused(self):
        (self.root / "source.py").write_text("new")
        with self.assertRaises(RuntimeError): self.run_publish()
        self.assertEqual(self.git("diff", "--cached", "--name-only"), b"")

    def test_staged_changes_refused(self):
        (self.root / "source.py").write_text("new")
        self.git("add", "source.py")
        with self.assertRaises(RuntimeError): self.run_publish()

    def test_push_failure_propagates(self):
        with self.assertRaises(subprocess.CalledProcessError): self.run_publish(fail_push=True)

    def test_retry_push_without_diff(self):
        result, calls = self.run_publish()
        self.assertIsNone(result)
        self.assertIn(("push",), calls)

    def test_deleted_output_is_staged(self):
        (self.root / "docs/index.html").unlink()
        result, _ = self.run_publish()
        self.assertEqual(result, ["docs/index.html"])
        self.assertEqual(self.git("ls-tree", "--name-only", "HEAD", "docs/index.html"), b"")


class BuildTests(unittest.TestCase):
    def namespace(self):
        tree = ast.parse((ROOT / "build_site.py").read_text(encoding="utf-8"))
        funcs = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        ns = {"logger": logging.getLogger("test"),
              "sys": types.SimpleNamespace(argv=["build_site.py"], executable=sys.executable),
              "os": os, "Path": Path, "__file__": str(ROOT / "build_site.py"), "subprocess": subprocess}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), "build_site.py", "exec"), ns)
        return ns

    def test_disconnect_on_backfill_failure(self):
        ns = self.namespace()
        with tempfile.TemporaryDirectory() as temp:
            client = types.SimpleNamespace(disconnect=AsyncMock())
            ns.update(OUTPUT_DIR=temp, IMAGES_DIR=temp, PIL_AVAILABLE=True,
                      PROCESSED_FILE="p", META_FILE="m", VISITS_FILE="v", PROXY_LIST=[],
                      load_json=lambda p, default: default,
                      refresh_targets=lambda p: None,
                      require_credentials=lambda: (1,"hash","phone"),
                      connect_with_proxy=AsyncMock(return_value=client),
                      backfill_links=AsyncMock(side_effect=RuntimeError("injected")))
            with self.assertRaises(RuntimeError): asyncio.run(ns["main"]())
            client.disconnect.assert_awaited_once()

    def test_publication_does_not_run_tests(self):
        ns = self.namespace()
        ns["publish_generated"] = Mock(return_value=["docs/index.html"])
        with patch.object(Path, "cwd", return_value=ROOT), patch.object(subprocess, "run") as run:
            result = ns["push_to_github"]()
        run.assert_not_called()
        ns["publish_generated"].assert_called_once_with(ROOT)
        self.assertEqual(result, ["docs/index.html"])

    def test_no_test_commands_in_builder(self):
        source = (ROOT / "build_site.py").read_text(encoding="utf-8")
        for command in ("tests/run.js", "tests/test_safety.py", "playwright install", "npm ci"):
            self.assertNotIn(command, source)

    def test_critical_generators_are_not_swallowed(self):
        tree = ast.parse((ROOT / "build_site.py").read_text(encoding="utf-8"))
        main = next(n for n in tree.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")
        calls = [n for n in main.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                 and isinstance(n.value.func, ast.Attribute) and n.value.func.attr == "run"]
        self.assertEqual(len(calls), 2)
        for n in calls:
            self.assertTrue(next(k.value.value for k in n.value.keywords if k.arg == "check"))

    def test_safety_exports(self):
        for name in ("GENERATED_FILES", "atomic_json", "git", "publish_generated", "publishable"):
            self.assertIn(name, safety.__all__)


if __name__ == "__main__":
    unittest.main(verbosity=2)
