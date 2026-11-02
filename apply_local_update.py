#!/usr/bin/env python3
"""Local-only proposal for Old Picture Art. No GitHub/network access."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile

def identity(x):
    return (x.get("title"), x.get("venue"), x.get("start"), x.get("end"), x.get("url"))

def blob_sha(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest()

def write_atomic(path, data):
    text = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    fd, tempname = tempfile.mkstemp(prefix="."+path.name+".", dir=str(path.parent), text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as out:
            out.write(text)
        os.replace(tempname, path)
    finally:
        if os.path.exists(tempname):
            os.unlink(tempname)

parser = argparse.ArgumentParser(description="Review or locally apply the 2026-11-02 archive proposal")
parser.add_argument("--dir", default=".", help="Folder containing the live afisha.json and afisha_archive.json")
parser.add_argument("--apply", action="store_true", help="Explicitly write local files; otherwise only preview")
args = parser.parse_args()
repo_dir = Path(args.dir).resolve()
proposal_path = Path(__file__).resolve().with_name("archive_changes.json")
proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
main_path = repo_dir / "afisha.json"
archive_path = repo_dir / "afisha_archive.json"
for path in (main_path, archive_path):
    if not path.is_file():
        parser.error(f"File not found: {path}")

main_raw = main_path.read_bytes()
archive_raw = archive_path.read_bytes()
main = json.loads(main_raw.decode("utf-8-sig"))
old_archive = json.loads(archive_raw.decode("utf-8-sig"))
if not isinstance(main.get("exhibitions"), list) or not isinstance(old_archive.get("exhibitions"), list):
    parser.error("Invalid JSON structure: exhibitions must be a list")
if "sources" not in main:
    parser.error("No sources key found in afisha.json; refusing to proceed")

to_archive = proposal["archive_exhibitions"]
wanted = {identity(x): x for x in to_archive}
if len(wanted) != len(to_archive):
    parser.error("Duplicate identities in proposal")
current_ids = [identity(x) for x in main["exhibitions"]]
archived_ids = [identity(x) for x in old_archive["exhibitions"]]
for key in wanted:
    if current_ids.count(key) > 1 or archived_ids.count(key) > 1:
        parser.error(f"Ambiguous duplicated exhibition identity: {key}")
    if key not in current_ids and key not in archived_ids:
        parser.error(f"Exhibition not found in either current or archive file: {key}")

new_main = copy.deepcopy(main)
new_archive = copy.deepcopy(old_archive)
new_main["exhibitions"] = [x for x in main["exhibitions"] if identity(x) not in wanted]
for exhibition in main["exhibitions"]:
    if identity(exhibition) in wanted and identity(exhibition) not in archived_ids:
        new_archive["exhibitions"].append(copy.deepcopy(exhibition))
if new_main["exhibitions"] != main["exhibitions"]:
    new_main["updated"] = "2026-11-02"
if new_archive["exhibitions"] != old_archive["exhibitions"]:
    new_archive["updated"] = "2026-11-02"

# Verify that only exhibition moves and updated dates can change.
assert new_main["sources"] == main["sources"]
assert len(main["exhibitions"]) - len(new_main["exhibitions"]) == sum(k in current_ids for k in wanted)
print("GitHub: no actions; this script touches LOCAL FILES ONLY.")
print(f"Current: {len(main['exhibitions'])} -> {len(new_main['exhibitions'])}")
print(f"Archive: {len(old_archive['exhibitions'])} -> {len(new_archive['exhibitions'])}")
print(f"Sources: {len(main['sources'])} -> {len(new_main['sources'])}")
if blob_sha(main_raw) != proposal["base_afisha_git_blob_sha"]:
    print("ATTENTION: Local afisha.json differs from the snapshot of main; only exact records will be moved.")
if not args.apply:
    print("DRY RUN ONLY. To perform this update locally, rerun with --apply.")
else:
    backups = []
    for p in (main_path, archive_path):
        backup = p.with_name(p.name + ".bak-2026-11-02")
        if backup.exists():
            parser.error(f"Backup already exists, refusing overwrite: {backup}")
        shutil.copy2(p, backup)
        backups.append(backup)
    write_atomic(main_path, new_main)
    write_atomic(archive_path, new_archive)
    print("Done. Local JSON files updated. Backups: " + ", ".join(p.name for p in backups))
