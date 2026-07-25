#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人格包卫生：默认每人/角色仅一个 persona；runs 只留最新。

用法：
  pythonw hygiene_persona.py --persona PATH --keep-runs 1
  pythonw hygiene_persona.py --examples-root PATH --character soseki --list-dupes
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


def is_run_dir(p: Path) -> bool:
    if not p.is_dir():
        return False
    if p.name.startswith("_"):
        return False
    if p.name == "loop_state.json":
        return False
    # r1 / r2 / run-1
    return bool(p.name)


def prune_runs(persona: Path, keep: int, dry: bool) -> dict:
    runs = persona / "runs"
    if not runs.is_dir():
        return {"pruned": [], "kept": [], "note": "no runs/"}
    dirs = [d for d in runs.iterdir() if d.is_dir() and not d.name.startswith("_")]
    dirs.sort(key=lambda d: d.stat().st_mtime, reverse=True)
    kept = dirs[:keep]
    prune = dirs[keep:]
    removed = []
    for d in prune:
        removed.append(str(d))
        if not dry:
            shutil.rmtree(d, ignore_errors=True)
    # 清理临时 metrics
    for name in ("_last_draft_metrics.json",):
        f = runs / name
        # 保留 loop_state
        pass
    return {
        "kept": [str(k) for k in kept],
        "pruned": removed,
        "keep_runs": keep,
        "dry_run": dry,
    }


def find_dupes(examples: Path, character: str) -> list[str]:
    hits = []
    if not examples.is_dir():
        return hits
    key = character.lower()
    for p in examples.rglob("rules.md"):
        persona = p.parent
        rel = str(persona).lower()
        if key in rel and (persona / "sample.md").exists():
            hits.append(str(persona))
    return hits


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, default=None)
    ap.add_argument("--keep-runs", type=int, default=1)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--examples-root", type=Path, default=None)
    ap.add_argument("--character", type=str, default="")
    ap.add_argument("--list-dupes", action="store_true")
    args = ap.parse_args()

    report: dict = {"ok": True}

    if args.list_dupes:
        root = args.examples_root
        if not root:
            root = Path(__file__).resolve().parents[1] / "examples"
        hits = find_dupes(root, args.character or "")
        report["dupes"] = hits
        report["count"] = len(hits)
        report["policy"] = "一个人物默认一个人格包；>1 须用户明文多包"
        report["ok"] = len(hits) <= 1 if args.character else True
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["ok"] else 1

    if not args.persona:
        print(json.dumps({"ok": False, "error": "need --persona or --list-dupes"}, ensure_ascii=False))
        return 2

    report["prune"] = prune_runs(args.persona.resolve(), args.keep_runs, args.dry_run)
    # 保留 loop_state
    ls = args.persona / "runs" / "loop_state.json"
    report["loop_state_present"] = ls.exists()
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
