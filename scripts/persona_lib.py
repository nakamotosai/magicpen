#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""人格库路径解析：默认 ~/.claude/kakashi/personas/<id>。"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

SKILL_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LIB = Path.home() / ".claude" / "kakashi" / "personas"


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def sanitize_id(raw: str) -> str:
    s = re.sub(r"[^\w一-鿿\-]+", "-", raw.strip(), flags=re.UNICODE)
    s = re.sub(r"-+", "-", s).strip("-").lower()
    return s or "persona"


def resolve_persona(spec: str | Path) -> Path:
    """PATH 或 id → 绝对 persona 目录。"""
    p = Path(spec)
    if p.is_dir() and ((p / "sample.md").exists() or (p / "rules.md").exists()):
        return p.resolve()
    # id in default lib
    cand = DEFAULT_LIB / str(spec)
    if cand.is_dir():
        return cand.resolve()
    # skill examples shallow search
    examples = SKILL_ROOT / "examples"
    if examples.is_dir():
        for rules in examples.rglob("rules.md"):
            parent = rules.parent
            if parent.name == str(spec) or parent.name.endswith(str(spec)):
                return parent.resolve()
            if str(spec) in parent.as_posix():
                # prefer exact id folder name
                if parent.name == f"persona-{spec}" or parent.name == spec:
                    return parent.resolve()
    raise FileNotFoundError(f"persona not found: {spec} (lib={DEFAULT_LIB})")


def lib_persona_dir(pid: str) -> Path:
    return DEFAULT_LIB / sanitize_id(pid)


def write_persona_meta(persona: Path, meta: dict) -> None:
    persona.mkdir(parents=True, exist_ok=True)
    path = persona / "persona.json"
    old = {}
    if path.exists():
        try:
            old = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            old = {}
    old.update(meta)
    old["updated_at"] = utc_now()
    path.write_text(json.dumps(old, ensure_ascii=False, indent=2), encoding="utf-8")


def list_personas() -> list[dict]:
    out = []
    if not DEFAULT_LIB.is_dir():
        return out
    for d in sorted(DEFAULT_LIB.iterdir()):
        if not d.is_dir():
            continue
        meta = {}
        mp = d / "persona.json"
        if mp.exists():
            try:
                meta = json.loads(mp.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        out.append({"id": d.name, "path": str(d), **meta})
    return out
