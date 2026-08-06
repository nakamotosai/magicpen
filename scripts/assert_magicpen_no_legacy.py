#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kill: magicpen skill must not keep a second entry dir or old product brand strings."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT.parent
# 旧兼容目录名（不得存在；原 skill 名为 kakashi）
LEGACY_DIR_NAME = "kakashi"
LEGACY_DIR = SKILLS / LEGACY_DIR_NAME

# 活表面禁止的旧品牌（拆写避免本文件自检命中）
_OLD_CN = "卡" + "卡西"
_OLD_JP = "カ" + "カシ"
_OLD_EN = "kakashi"
_OLD_COPY = "拷贝忍者"

FORBIDDEN = [
    re.compile(r"\b" + re.escape(_OLD_EN) + r"\b", re.I),
    re.compile(r"\b" + re.escape(_OLD_COPY) + r"\b"),
    re.compile(re.escape(_OLD_CN)),
    re.compile(re.escape(_OLD_JP)),
    re.compile(r"skills[/\\]" + re.escape(_OLD_EN)),
]

SCAN_GLOBS = [
    "SKILL.md",
    "README.md",
    "scripts/*.py",
    "references/*.md",
]

EXTRA_FILES = [
    Path.home() / ".omp" / "SPECS" / "style-clone-skill-20260724" / "spec.md",
    Path.home() / ".omp" / "SPECS" / "style-clone-skill-20260724" / "pipeline-v3-user-lock.md",
    Path.home() / ".omp" / "SPECS" / "style-clone-skill-20260724" / "naming-candidates.md",
]


def collect() -> list[Path]:
    files: list[Path] = []
    for g in SCAN_GLOBS:
        files.extend(ROOT.glob(g))
    for p in EXTRA_FILES:
        if p.is_file():
            files.append(p)
    examples = ROOT / "examples"
    if examples.is_dir():
        for p in examples.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".md", ".py", ".json", ".txt", ".yml", ".yaml"}:
                files.append(p)
    seen: set[Path] = set()
    out: list[Path] = []
    for f in files:
        try:
            r = f.resolve()
        except OSError:
            continue
        if r in seen:
            continue
        seen.add(r)
        out.append(f)
    return out


def main() -> int:
    errors: list[str] = []
    if LEGACY_DIR.exists():
        errors.append(f"LEGACY_DIR_EXISTS: {LEGACY_DIR}")

    skill = ROOT / "SKILL.md"
    if not skill.is_file():
        errors.append("MISSING_SKILL_MD")
    else:
        head = skill.read_text(encoding="utf-8", errors="replace")[:500]
        if "name: magicpen" not in head:
            errors.append("SKILL_NAME_NOT_MAGICPEN")
        if re.search(r"name:\s*" + re.escape(_OLD_EN) + r"\b", head):
            errors.append("SKILL_STILL_NAMED_LEGACY")
        # 触发词不得再挂旧品牌
        if _OLD_CN in head or _OLD_JP in head or re.search(r"\b" + re.escape(_OLD_EN) + r"\b", head, re.I):
            errors.append("SKILL_TRIGGERS_STILL_LEGACY")

    if (ROOT / "examples" / "self-demo-voice").exists():
        errors.append("SELF_DEMO_VOICE_STILL_PRESENT")

    skip_names = {Path(__file__).name}
    for f in collect():
        if f.name in skip_names or f.name.startswith("_"):
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            errors.append(f"READ_FAIL {f}: {e}")
            continue
        for pat in FORBIDDEN:
            if pat.search(text):
                rel = str(f)
                try:
                    rel = str(f.relative_to(ROOT))
                except ValueError:
                    pass
                errors.append(f"{rel}: matched {pat.pattern}")
                break

    if errors:
        print("FAIL assert_magicpen_no_legacy")
        for e in errors[:100]:
            print(" -", e)
        if len(errors) > 100:
            print(f" ... +{len(errors) - 100} more")
        return 1
    print("PASS assert_magicpen_no_legacy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
