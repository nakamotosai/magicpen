#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中段防提纲：分节文每节须有场面/查证动作痕迹（v3.5）。

仅在 draft 含 ≥3 个中文编号节（## 一、或 一、）时启用。
短文/无分节 → ok skip。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCENE_PAT = re.compile(
    r"查|翻|搜|对照|对了一下|打开|点开|刷到|群里|私信|热搜|截图|"
    r"答弁|记者会|会议录|原文|日文源|现场|门口|地铁|便利店|"
    r"敲|站在|握手|塞|摊在|勾|画圈|台灯|名单|名单|脚步|掌心|"
    r"满脸问号|好家伙|我去|我盯|我看|我听|看见|听见|问我"
)

ABSTRACT_HEAVY = re.compile(
    r"总之|综上所述|本质上|从某种意义|历史性|时代|叙事|话语权|基本盘"
)


def split_sections(text: str) -> list[tuple[str, str]]:
    lines = text.replace("\r\n", "\n").split("\n")
    sections: list[tuple[str, str]] = []
    cur_title = "__lead__"
    buf: list[str] = []
    title_re = re.compile(r"^(?:#{1,3}\s*)?([一二三四五六七八九十]、\S.*)$")
    for ln in lines:
        m = title_re.match(ln.strip())
        if m:
            if buf or cur_title != "__lead__":
                sections.append((cur_title, "\n".join(buf).strip()))
            cur_title = m.group(1).strip()
            buf = []
        else:
            buf.append(ln)
    sections.append((cur_title, "\n".join(buf).strip()))
    return sections


def score_section(body: str) -> dict:
    if not body.strip():
        return {"ok": False, "scene_hits": 0, "reason": "empty"}
    hits = SCENE_PAT.findall(body)
    # unique-ish
    hit_n = len(hits)
    abs_n = len(ABSTRACT_HEAVY.findall(body))
    # 日期堆叠旁证：过多年份且无场面 → 提纲
    years = re.findall(r"19\d{2}|20\d{2}", body)
    ok = hit_n >= 1
    if len(years) >= 4 and hit_n == 0:
        ok = False
    if abs_n >= 3 and hit_n <= 1:
        ok = False
    return {
        "ok": ok,
        "scene_hits": hit_n,
        "abstract_hits": abs_n,
        "year_hits": len(years),
        "reason": None if ok else "no_scene_or_outline_like",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None)
    ap.add_argument("--min-sections", type=int, default=3)
    ap.add_argument("--min-ok-ratio", type=float, default=0.67)
    args = ap.parse_args()

    draft = args.draft.read_text(encoding="utf-8") if args.draft.exists() else ""
    secs = split_sections(draft)
    numbered = [(t, b) for t, b in secs if t != "__lead__" and re.match(r"^[一二三四五六七八九十]、", t)]
    if len(numbered) < args.min_sections:
        report = {
            "ok": True,
            "gate": "section_scene",
            "skipped": True,
            "reason": f"numbered_sections={len(numbered)} < {args.min_sections}",
            "sections": [],
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    details = []
    ok_n = 0
    for t, b in numbered:
        sc = score_section(b)
        if sc["ok"]:
            ok_n += 1
        details.append({"title": t, **sc, "han": len(re.findall(r"[一-鿿]", b))})
    ratio = ok_n / max(len(numbered), 1)
    ok = ratio >= args.min_ok_ratio
    report = {
        "ok": ok,
        "gate": "section_scene",
        "skipped": False,
        "ok_sections": ok_n,
        "total_sections": len(numbered),
        "ok_ratio": round(ratio, 3),
        "min_ok_ratio": args.min_ok_ratio,
        "sections": details,
        "note": "分节文每节须有场面/查证动作；提纲履历堆叠会失败",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
