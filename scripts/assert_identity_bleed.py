#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写后硬闸：样本身份/角色壳是否串进 draft。

默认：brief 未明文「角色仿写/同世界观」时，禁止把 sample 叙事者壳写进新文。
可选 persona/identity_ban.txt（一行一词/短语）追加禁表。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 仅「明文允许」才跳过；「禁止角色仿写」不得误触发
ROLEPLAY_OK = re.compile(
    r"(?:允许|可以|需要|要求|请|要)[^。\n]{0,12}(?:角色仿写|同世界观|续写样本|猫叙事|咱家口吻|身份壳)"
    r"|(?:角色仿写|同世界观|续写样本)[^。\n]{0,8}(?:可以|允许|开启)"
    r"|可用猫|可用「?咱家|允许身份壳",
    re.I,
)
ROLEPLAY_DENY = re.compile(r"禁止[^。\n]{0,16}(?:角色仿写|同世界观|猫|咱家|身份壳)", re.I)

# 常见文学壳；仅当 sample 也出现时才启用（避免误伤「猫」字成语）
CONDITIONAL_SHELLS = [
    "咱家",
    "吾辈",
    "本猫",
    "鱼干",
    "秋刀鱼",
    "书生",
    "阿三",
    "茅厕先生",
    "三花",
]


def han_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def load_sample(persona: Path) -> str:
    for name in ("sample.md", "train.md", "SAMPLE.md"):
        p = persona / name
        if p.exists():
            return p.read_text(encoding="utf-8")
    return ""


def infer_bans(sample: str, ban_file: Path | None) -> list[str]:
    bans: list[str] = []
    for tok in CONDITIONAL_SHELLS:
        if tok in sample:
            bans.append(tok)
    # 「是猫 / 咱家是猫」强身份
    if re.search(r"是猫|猫。|猫，", sample) and "猫" not in bans:
        # 仅当样本高频自称猫时启用单字「猫」——过宽，改用短语
        if "咱家是猫" in sample or "吾辈是猫" in sample:
            bans.append("咱家是猫")
            bans.append("吾辈是猫")
            if "猫" not in bans:
                bans.append("猫")
    if ban_file and ban_file.exists():
        for ln in ban_file.read_text(encoding="utf-8").splitlines():
            s = ln.strip()
            if s and not s.startswith("#"):
                bans.append(s)
    # 去重保序
    seen = set()
    out = []
    for b in bans:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    draft = args.draft.read_text(encoding="utf-8") if args.draft.exists() else ""
    brief = ""
    if args.brief and args.brief.exists():
        brief = args.brief.read_text(encoding="utf-8")
    sample = load_sample(args.persona)

    if ROLEPLAY_DENY.search(brief):
        # 明确禁止 → 不跳过
        pass
    elif ROLEPLAY_OK.search(brief):
        report = {
            "ok": True,
            "skipped": True,
            "reason": "brief allows roleplay/identity shell",
            "hits": [],
            "bans_active": [],
        }
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            args.out.write_text(text, encoding="utf-8")
        print(text)
        return 0

    bans = infer_bans(sample, args.persona / "identity_ban.txt")
    hits = []
    for b in bans:
        if b and b in draft:
            hits.append({"token": b, "count": draft.count(b)})

    report = {
        "ok": len(hits) == 0,
        "skipped": False,
        "hits": hits,
        "bans_active": bans,
        "draft_han": han_count(draft),
        "persona": str(args.persona),
        "draft": str(args.draft),
        "note": "硬闸：风格≠身份；命中则回炉 Writer",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
