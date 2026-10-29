"""Atomic JSON writes and automatic project commits, without local tests."""
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from datetime import datetime


def atomic_json(path, data, backup=True):
    target = Path(path)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink(): raise ValueError(f"Refusing symlink: {target}")
    tmp = backup_tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                dir=target.parent, prefix="." + target.name + ".", suffix=".tmp", delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            shutil.copymode(target, tmp)
            if backup:
                with target.open(encoding="utf-8") as old: json.load(old)
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False,
                        prefix="." + target.name + ".", suffix=".tmp") as b:
                    backup_tmp = Path(b.name)
                shutil.copyfile(target, backup_tmp)
                os.replace(backup_tmp, target.with_name(target.name + ".bak"))
        os.replace(tmp, target)
    finally:
        for item in (tmp, backup_tmp):
            if item is not None: item.unlink(missing_ok=True)


GENERATED_FILES = frozenset({
    "posts_meta.json", "visits_meta.json", "processed_ids.json",
    "medium_dictionary.json", "image_sizes.json", "artist_info.json",
    "museum_coordinates.json", "afisha_places.json",
})


def publishable(path):
    """Source and generated files are allowed; Git ignore rules also apply."""
    normalized = os.fspath(path).replace("\\", "/")
    parts = normalized.split("/")
    if not parts or normalized.startswith("/") or ".." in parts or ":" in parts[0]:
        return False
    blocked_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".conda",
                    ".idea", ".vscode", "hires", "output"}
    if any(part in blocked_dirs for part in parts): return False
    if normalized.startswith("docs/_unused/"): return False
    for part in parts:
        low = part.lower()
        if low == ".env" or low.startswith(".env."): return False
        if low.endswith((".session", ".session-journal", ".key", ".pem", ".secret",
                         ".bak", ".tmp", ".pyc", ".pyo", ".orig", ".rej", ".zip", "~")):
            return False
        if low.endswith(".log") or ".log." in low: return False
    return True


def git(*args, data=None):
    try:
        result = subprocess.run(["git", *args], input=data, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)}: {detail or 'command failed'}") from exc
    return result.stdout


def _paths(data):
    return [os.fsdecode(p) for p in data.split(b"\0") if p]


def publish_generated(root):
    """Commit source + content automatically, then push. Does not run tests."""
    root = Path(root).resolve()
    actual = Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve()
    if actual != root: raise RuntimeError("Run publication from the repository root")
    # Existing ordinary staged edits are accepted. Credentials are never committed here.
    staged_before = _paths(git("diff", "--cached", "--name-only", "-z"))
    blocked = [p for p in staged_before if not publishable(p)]
    if blocked:
        raise RuntimeError("Excluded files are already staged. Unstage them first: " + ", ".join(blocked))
    changed = _paths(git("diff", "HEAD", "--name-only", "-z"))
    untracked = _paths(git("ls-files", "--others", "--exclude-standard", "-z"))
    candidates = sorted(set(changed + untracked))
    paths = [p for p in candidates if publishable(p)]
    omitted = [p for p in candidates if not publishable(p)]
    if omitted:
        logging.getLogger("build_site").warning("Не добавлены временные/закрытые файлы: %s", ", ".join(omitted))
    if paths:
        for name in paths:
            target = root / name
            if target.is_symlink() or not target.resolve().is_relative_to(root):
                raise RuntimeError("Unsafe output path: " + name)
        data = b"\0".join(os.fsencode(p) for p in paths) + b"\0"
        git("--literal-pathspecs", "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul", data=data)
    staged = _paths(git("diff", "--cached", "--name-only", "-z"))
    if any(not publishable(p) for p in staged):
        raise RuntimeError("Excluded file in Git index; commit cancelled")
    if staged:
        git("commit", "-m", f"Авто-обновление: {datetime.now():%Y-%m-%d %H:%M}")
        logging.getLogger("build_site").info("Создан коммит: %s файлов", len(staged))
    else:
        logging.getLogger("build_site").info("Новых изменений для коммита нет")
    git("push")
    logging.getLogger("build_site").info("GitHub: отправлено")
    return staged or None


__all__ = ["GENERATED_FILES", "atomic_json", "publishable", "git", "publish_generated"]
