#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写后硬闸：样本事件/专名串戏（富士山问题）。

只查 content_ban.txt 整词；不做激进 n-gram（会误伤「在东京的上海人」等口气指纹）。
brief 已写的词豁免。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load_bans(persona: Path) -> list[str]:
    bans: list[str] = []
    p = persona / "content_ban.txt"
    if p.exists():
        for ln in p.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s and not s.startswith("#"):
                bans.append(s)
    return bans


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None)
    args = ap.parse_args()

    draft = args.draft.read_text(encoding="utf-8")
    brief = args.brief.read_text(encoding="utf-8") if args.brief and args.brief.exists() else ""
    bans = load_bans(args.persona.resolve())

    hits = []
    for b in bans:
        if len(b) < 2:
            continue
        if b in brief:
            continue
        if b in draft:
            hits.append(b)

    ok = len(hits) == 0
    report = {
        "ok": ok,
        "gate": "content_bleed",
        "ban_hits": hits,
        "ban_size": len(bans),
        "note": "样本事件/专名串戏；brief 已写专名豁免；不做 n-gram 误伤口气指纹",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
