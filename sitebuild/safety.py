"""Atomic JSON writes and explicitly scoped publication. Standard library only."""
import json
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
    if target.is_symlink():
        raise ValueError(f"Refusing symlink: {target}")
    tmp = None
    backup_tmp = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         dir=target.parent, prefix="." + target.name + ".",
                                         suffix=".tmp", delete=False) as stream:
            tmp = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if target.exists():
            shutil.copymode(target, tmp)
            if backup:
                with target.open(encoding="utf-8") as old:
                    json.load(old)
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False,
                                                 prefix="." + target.name + ".", suffix=".tmp") as b:
                    backup_tmp = Path(b.name)
                shutil.copyfile(target, backup_tmp)
                os.replace(backup_tmp, target.with_name(target.name + ".bak"))
        os.replace(tmp, target)
    finally:
        for item in (tmp, backup_tmp):
            if item is not None:
                item.unlink(missing_ok=True)


GENERATED_FILES = frozenset({
    "posts_meta.json", "visits_meta.json", "processed_ids.json",
    "medium_dictionary.json", "image_sizes.json", "artist_info.json",
    "museum_coordinates.json", "afisha_places.json",
})


def publishable(path):
    parts = Path(path).parts
    if not parts or Path(path).is_absolute() or ".." in parts:
        return False
    if any(p.endswith((".bak", ".tmp", ".session", ".session-journal"))
           or p == ".env" or p.startswith(".env.") for p in parts):
        return False
    return path in GENERATED_FILES or (len(parts) > 1 and parts[0] == "docs")


def git(*args, data=None):
    result = subprocess.run(["git", *args], input=data, stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE, check=True)
    return result.stdout


def _paths(data):
    return [os.fsdecode(p) for p in data.split(b"\0") if p]


def publish_generated(root):
    root = Path(root).resolve()
    if Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve() != root:
        raise RuntimeError("Run publication from the repository root")
    if git("diff", "--cached", "--name-only", "-z"):
        raise RuntimeError("Git index is not empty. Commit or unstage your changes first.")
    changed = _paths(git("diff", "HEAD", "--name-only", "-z"))
    untracked = _paths(git("ls-files", "--others", "--exclude-standard", "-z"))
    unexpected = [p for p in changed if not publishable(p)]
    if unexpected:
        raise RuntimeError("Commit source changes separately before publishing: " + ", ".join(unexpected))
    paths = sorted({p for p in changed + untracked if publishable(p)})
    if paths:
        for name in paths:
            if (root / name).is_symlink() or not (root / name).resolve().is_relative_to(root):
                raise RuntimeError("Unsafe output path: " + name)
        data = b"\0".join(os.fsencode(p) for p in paths) + b"\0"
        git("--literal-pathspecs", "add", "-A", "--pathspec-from-file=-",
            "--pathspec-file-nul", data=data)
        staged = _paths(git("diff", "--cached", "--name-only", "-z"))
        if any(not publishable(p) for p in staged):
            raise RuntimeError("Unexpected staged file; refusing to commit")
        if staged:
            git("commit", "-m", f"Авто-обновление: {datetime.now():%Y-%m-%d %H:%M}")
    git("push")
    return paths or None


__all__ = ["GENERATED_FILES", "atomic_json", "git", "publish_generated", "publishable"]
