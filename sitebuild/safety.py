"""Безопасная атомарная запись JSON и автоматическая публикация без локальных тестов."""

from datetime import datetime
import json
import logging
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def atomic_json(path, data, backup=True):
    """Атомарная замена JSON с необязательной резервной копией."""
    target = Path(path)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        raise ValueError(f"Refusing symlink: {target}")
    tmp = backup_tmp = None
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
                                                 prefix="." + target.name + ".",
                                                 suffix=".tmp") as back:
                    backup_tmp = Path(back.name)
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

# Отсекаем типовые приватные конфиги, ключи и бинарные базы. Это именно
# дополнительная страховка: секреты не следует хранить даже в рабочей копии Git.
_BLOCKED_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".conda",
    ".idea", ".vscode", "hires", "output", ".aws", ".ssh", ".secrets",
    ".terraform", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox",
})
_BLOCKED_NAMES = frozenset({
    ".npmrc", ".pypirc", ".netrc", ".htpasswd", ".envrc", ".ds_store",
    "id_rsa", "id_ed25519", "id_ecdsa", "id_dsa", "credentials.json",
    "service-account.json", "service_account.json", "secrets.json", "token.json",
})
_BLOCKED_ENDINGS = (
    ".session", ".session-journal", ".key", ".pem", ".secret",
    ".bak", ".tmp", ".pyc", ".pyo", ".orig", ".rej", ".zip", "~",
    ".p12", ".pfx", ".jks", ".keystore", ".sqlite", ".sqlite3", ".db",
    ".log",
)


def publishable(path):
    """Разрешены только относительные пути без типичных секретов/кэшей."""
    normalized = os.fspath(path).replace("\\", "/")
    parts = normalized.split("/")
    if (not normalized or normalized.startswith("/") or ":" in parts[0]
            or any(p in {"", ".", ".."} for p in parts)):
        return False
    if any(part.lower() in _BLOCKED_DIRS for part in parts[:-1]):
        return False
    if normalized.startswith("docs/_unused/"):
        return False
    for part in parts:
        low = part.lower()
        if low == ".env" or low.startswith(".env."):
            return False
        if low in _BLOCKED_NAMES or low.endswith(_BLOCKED_ENDINGS):
            return False
        if ".log." in low:
            return False
    return True


def git(*args, data=None):
    """Выполнить git, передавая имена путей безопасно через stdin."""
    try:
        result = subprocess.run(["git", *args], input=data, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, check=True)
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"git {' '.join(args)}: {detail or 'command failed'}") from exc
    return result.stdout


def _paths(data):
    return [os.fsdecode(path) for path in data.split(b"\0") if path]


def publish_generated(root):
    """Коммит разрешённых исходников и контента, затем push. Без запуска тестов."""
    root = Path(root).resolve()
    actual = Path(os.fsdecode(git("rev-parse", "--show-toplevel")).strip()).resolve()
    if actual != root:
        raise RuntimeError("Run publication from the repository root")
    staged_before = _paths(git("diff", "--cached", "--name-only", "-z"))
    blocked = [name for name in staged_before if not publishable(name)]
    if blocked:
        raise RuntimeError("Excluded files are already staged. Unstage them first: " + ", ".join(blocked))

    changed = _paths(git("diff", "HEAD", "--name-only", "-z"))
    untracked = _paths(git("ls-files", "--others", "--exclude-standard", "-z"))
    candidates = sorted(set(changed + untracked))
    paths = [name for name in candidates if publishable(name)]
    omitted = [name for name in candidates if not publishable(name)]
    if omitted:
        logging.getLogger("build_site").warning(
            "Не добавлены временные/закрытые файлы: %s", ", ".join(omitted))
    if paths:
        for name in paths:
            target = root / name
            if target.is_symlink() or not target.resolve().is_relative_to(root):
                raise RuntimeError("Unsafe output path: " + name)
        data = b"\0".join(os.fsencode(name) for name in paths) + b"\0"
        git("--literal-pathspecs", "add", "-A", "--pathspec-from-file=-", "--pathspec-file-nul", data=data)
    staged = _paths(git("diff", "--cached", "--name-only", "-z"))
    if any(not publishable(name) for name in staged):
        raise RuntimeError("Excluded file in Git index; commit cancelled")
    # Файлы, уже находившиеся в индексе, проверяем на симлинки тоже.
    for name in staged:
        target = root / name
        if target.is_symlink() or (target.exists() and not target.resolve().is_relative_to(root)):
            raise RuntimeError("Unsafe staged path: " + name)
    if staged:
        git("commit", "-m", f"Авто-обновление: {datetime.now():%Y-%m-%d %H:%M}")
        logging.getLogger("build_site").info("Создан коммит: %s файлов", len(staged))
    else:
        logging.getLogger("build_site").info("Новых изменений для коммита нет")
    git("push")
    logging.getLogger("build_site").info("GitHub: отправлено")
    return staged or None


__all__ = ["GENERATED_FILES", "atomic_json", "publishable", "git", "publish_generated"]
