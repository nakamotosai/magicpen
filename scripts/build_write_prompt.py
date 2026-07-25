#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装写稿提示词 v3.1：加载 persona → sample + rules.md + 用户条件 → WRITE_PROMPT。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def pick_sample(persona: Path) -> Path:
    for name in ("sample.md", "train.md", "SAMPLE.md"):
        p = persona / name
        if p.exists():
            return p
    raise FileNotFoundError(f"人格包缺 sample.md: {persona}")


def pick_rules(persona: Path) -> Path:
    p = persona / "rules.md"
    if p.exists():
        return p
    raise FileNotFoundError(f"人格包缺 rules.md（请先跑 style_sensors --rules）: {persona}")


def load_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def build(persona: Path, brief: str, genre: str | None) -> str:
    sample = load_text(pick_sample(persona))
    rules = load_text(pick_rules(persona))
    pid = persona.name
    genre_line = genre or "跟 brief；未指定则 essay/longform"

    notes = ""
    for name in ("NOTES.md", "extras.md", "USER.md"):
        np = persona / name
        if np.exists():
            notes = load_text(np)
            break

    parts: list[str] = []
    parts.append(f"# 卡卡西 · Writer 提示词（人格包 `{pid}`）\n\n")
    parts.append(
        "你是写稿分身。任务：按【原文样本】的**笔迹** + 【写作要领 rules】，完成【新文任务】。\n"
        "学写法，不学身份。不是润色 brief，不是摘要原文，不是续写样本故事。\n\n"
    )
    parts.append("## 0. 铁律\n\n")
    parts.append(
        "1. **原文样本 = 笔迹主参考**（句式、节奏、段落换行、冷嘲热度、收束方式）——"
        "**不是**角色设定库、世界观库、情节素材库。\n"
        "2. **rules.md = 不得违反的写作要领**（一行一条，全部遵守）。\n"
        "3. **新文任务 / 用户条件 = 当次事实、人称、题材、结构、长度**；笔迹不听网文默认腔。\n"
        "4. **风格 ≠ 身份**：禁止默认沿用样本叙事者身份/物种/职业/专名"
        "（如「咱家是猫」、书生、阿三、具体真人自号）与样本专属世界；"
        "除非 brief **明文**要求角色仿写或同世界观续写。\n"
        "5. 禁止把样本招牌词、章节壳、招牌道具 1:1 填空到新题当装饰。\n"
        "6. 只输出新文正文（除非任务要求标题）。\n"
    )
    parts.append("\n## 1. 原文样本（**仅笔迹** · 主参考）\n\n```text\n")
    parts.append(sample)
    parts.append(
        "\n```\n\n"
        "> 换行与分段是笔迹的一部分。\n"
        "> **勿**把样本里的「谁在说话、是什么物种/职业、住在哪、认识谁」当成新文默认设定；"
        "新文的人称与事实只听第 5 节 brief。\n"
    )
    parts.append("\n## 2. 写作要领（rules.md · 全文有效）\n\n")
    parts.append(rules)
    parts.append(f"\n\n## 3. 体裁\n\n{genre_line}\n")
    if notes:
        parts.append("\n## 4. 人格包备注\n\n")
        parts.append(notes)
        parts.append("\n")
    parts.append("\n## 5. 新文任务与用户条件\n\n")
    parts.append(brief.strip())
    parts.append("\n\n## 6. 输出\n\n只写新文正文。写完用 rules 自检再交稿。\n")
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True, help="人格包目录")
    ap.add_argument("--brief", type=Path)
    ap.add_argument("--brief-text", type=str)
    ap.add_argument("--genre", type=str, default=None)
    ap.add_argument("--out", type=Path, required=True)
    # 显式拒绝旧参数
    ap.add_argument("--voice", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.voice is not None:
        print(json.dumps({"ok": False, "error": "removed: use --persona only"}, ensure_ascii=False), file=sys.stderr)
        return 2

    if args.brief_text:
        brief = args.brief_text
    elif args.brief:
        brief = args.brief.read_text(encoding="utf-8")
    else:
        print("need --brief or --brief-text", file=sys.stderr)
        return 2

    try:
        text = build(args.persona.resolve(), brief, args.genre)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "chars": len(text), "persona": str(args.persona)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
