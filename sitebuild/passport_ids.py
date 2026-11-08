# -*- coding: utf-8 -*-
"""Persistent IDs for art-passport artists and museums.

The registry file is committed with the site. To retain an ID after a rename,
assign the old ID to the new display name in passport_registry.json.
"""
import hashlib
import json
import os
from pathlib import Path

PATH = Path(__file__).resolve().parent.parent / 'passport_registry.json'
_cache = None
_dirty = False


def _load():
    global _cache
    if _cache is None:
        try:
            raw = json.loads(PATH.read_text('utf-8'))
            if not isinstance(raw, dict):
                raw = {}
        except (OSError, ValueError):
            raw = {}
        _cache = {kind: dict(raw.get(kind) or {}) for kind in ('artists', 'museums')}
    return _cache


def get_passport_id(kind, name):
    """Stable ID from the persistent registry, not the current URL/label."""
    global _dirty
    if kind not in ('artists', 'museums'):
        raise ValueError('unsupported entity kind')
    name = str(name or '').strip()
    if not name:
        return ''
    table = _load()[kind]
    if name not in table:
        prefix = 'a_' if kind == 'artists' else 'm_'
        table[name] = prefix + hashlib.sha256((kind + '\0' + name).encode('utf-8')).hexdigest()[:24]
        _dirty = True
    return table[name]


def registry_aliases():
    """Map every known historic name to the same immutable entity ID."""
    return {k: dict(v) for k, v in _load().items()}


def save_passport_registry():
    global _dirty
    if not _dirty:
        return
    PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = PATH.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(_load(), ensure_ascii=False, indent=2, sort_keys=True) + '\n', 'utf-8')
    os.replace(tmp, PATH)
    _dirty = False
