# -*- coding: utf-8 -*-
"""Модули питона нужных версий — по requirements.txt.

Раньше сборка при каждом запуске делала pip install --upgrade: в любой
день могла приехать новая версия telethon или Pillow и сломать сборку без
единой правки в коде. Теперь версии закреплены в requirements.txt, и
сборка ставит модули, только если чего-то нет или стоит другая версия.
"""

import logging
import os
import re
import subprocess
import sys

logger = logging.getLogger("build_site")

REQUIREMENTS_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                 "requirements.txt")


def read_requirements(path=REQUIREMENTS_FILE):
    """{модуль: версия} из строк вида «имя==версия»; комментарии и -r пропускаются."""
    pins = {}
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.split("#", 1)[0].strip()
                m = re.match(r"([A-Za-z0-9_.\-]+)(\[[^\]]*\])?==([^\s;]+)$", line)
                if m:
                    pins[m.group(1)] = m.group(3)
    except OSError:
        pass
    return pins


def installed_version(name):
    from importlib import metadata
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def mismatched(pins, version_of=installed_version):
    """[(модуль, что стоит или None, что нужно)] — то, что надо поставить."""
    out = []
    for name, want in pins.items():
        have = version_of(name)
        if have != want:
            out.append((name, have, want))
    return out


def ensure_requirements(path=REQUIREMENTS_FILE, run=subprocess.check_call, version_of=installed_version):
    """Ставит модули из requirements.txt, если чего-то не хватает.

    "ok" — всё уже стояло, "installed" — поставил (в памяти ещё старые
    версии, сборку надо перезапустить), "failed" — не вышло, "no-file".
    """
    pins = read_requirements(path)
    if not pins:
        logger.warning(f"Нет файла {os.path.basename(path)} — модули не проверены")
        return "no-file"
    todo = mismatched(pins, version_of)
    if not todo:
        logger.info("Модули на месте (версии из requirements.txt)")
        return "ok"
    logger.info("Ставлю модули: " + ", ".join(
        f"{n} {have} → {want}" if have else f"{n} {want}" for n, have, want in todo))
    try:
        run([sys.executable, "-m", "pip", "install", "-r", path,
             "--quiet", "--disable-pip-version-check"])
        logger.info("Модули установлены")
        return "installed"
    except Exception as e:
        logger.warning(f"Не получилось поставить модули ({e}). Вручную: "
                       f"python -m pip install -r requirements.txt")
        return "failed"


__all__ = ['REQUIREMENTS_FILE', 'read_requirements', 'installed_version', 'mismatched', 'ensure_requirements']
