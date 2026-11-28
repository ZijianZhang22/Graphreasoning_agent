#!/usr/bin/env python3
"""Explicitly repin SWE-bench Lite *before* preparing a Task 2 manifest.

Run once after inspecting the output and before any issue is prepared.
This script does not access benchmark hidden solution fields.
"""
import json
import sys
import urllib.request
from pathlib import Path

path = Path(__file__).resolve().parent / "study.task2.json"
for arg in sys.argv[1:]:
    if arg != "--write":
        path = Path(arg).resolve()
if not path.exists():
    sys.exit(f"Missing study config: {path}")
data = json.loads(path.read_text(encoding="utf-8"))
name = data["dataset"]["name"]
url = f"https://huggingface.co/api/datasets/{name}"
with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent":"DocAgent-Task2-Setup"}), timeout=30) as res:
    sha = json.load(res)["sha"]
old = data["dataset"]["revision"]
print("Dataset:", name)
print("Configured revision:", old)
print("Currently served revision:", sha)
if old != sha:
    if "--write" not in sys.argv:
        sys.exit("Revision differs. Review it, then rerun: python3 pin_dataset_current.py --write")
    data["dataset"]["revision"] = sha
    backup = path.with_suffix(".original.json")
    if not backup.exists():
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("Pinned new revision. DO NOT modify after prepare.")
else:
    print("Pinned revision already matches served revision.")
