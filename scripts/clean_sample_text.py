#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""清洗创建人格用的范文 sample（贴入或网搜落盘后）。

目标：去掉网页壳、导航、重复空行，尽量只留可学笔迹的正文。
不代写、不补造正文。

  pythonw clean_sample_text.py --in raw.md --out raw.md
  pythonw clean_sample_text.py --text "…"   # stdout 含 text 的 JSON
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

HAN_RE = re.compile(r"[一-鿿]")
TAG_RE = re.compile(r"<[^>]+>")
MD_LINK_RE = re.compile(r"\[([^\]]+)\]\([^)]+\)")
URL_RE = re.compile(r"https?://\S+")
MULTI_NL = re.compile(r"\n{3,}")
MULTI_SP = re.compile(r"[ \t]{2,}")

NOISE_LINE = re.compile(
    r"^\s*("
    r"首页|主页|登录|注册|分享|收藏|点赞|评论|关注|订阅|举报|版权所有|"
    r"返回顶部|上一篇|下一篇|相关推荐|热门|导航|目录|"
    r"cookie|privacy|terms|subscribe|sign in|log in|follow us|"
    r"广告|推广|版权声明|转载请注明|"
    r"阅读\s*\d+|字数\s*\d+|浏览\s*\d+"
    r")\s*$",
    re.I,
)


def han_count(text: str) -> int:
    return len(HAN_RE.findall(text))


def clean_text(raw: str) -> dict:
    src = raw or ""
    before_han = han_count(src)
    t = src.replace("\r\n", "\n").replace("\r", "\n")
    t = TAG_RE.sub("", t)
    t = MD_LINK_RE.sub(r"\1", t)
    t = URL_RE.sub("", t)
    t = t.replace(" ", " ").replace("　", "  ")
    lines = []
    for line in t.split("\n"):
        s = line.strip()
        if not s:
            lines.append("")
            continue
        if NOISE_LINE.match(s):
            continue
        if re.fullmatch(r"[-_=*]{3,}", s):
            continue
        if len(s) <= 2 and not HAN_RE.search(s):
            continue
        lines.append(MULTI_SP.sub(" ", s))
    t = "\n".join(lines)
    t = MULTI_NL.sub("\n\n", t).strip()
    if t:
        t += "\n"
    after_han = han_count(t)
    notes = []
    if after_han < 500:
        notes.append("汉字不足 500，创建人格可能偏弱；建议补贴或再搜")
    if after_han > 3000:
        notes.append("超过 3000 汉字硬顶，下游 install 会截窗；可先人工删节")
    if after_han < before_han * 0.3 and before_han > 200:
        notes.append("清洗后字数骤降，请核对是否误删正文")
    return {
        "ok": True,
        "text": t,
        "han_before": before_han,
        "han_after": after_han,
        "bytes_after": len(t.encode("utf-8")),
        "notes": notes,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="kakashi clean sample text")
    ap.add_argument("--in", dest="inp", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--text", type=str, default=None)
    ap.add_argument("--include-text", action="store_true", help="即使写了 --out 也在 JSON 里带回 text")
    args = ap.parse_args()

    if args.text is not None:
        raw = args.text
    elif args.inp and args.inp.is_file():
        raw = args.inp.read_text(encoding="utf-8", errors="replace")
    else:
        print(json.dumps({"ok": False, "error": "need --in or --text"}, ensure_ascii=False))
        return 2

    report = clean_text(raw)
    out = args.out or (args.inp if args.inp and args.text is None else None)
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report["text"], encoding="utf-8")
        report["path"] = str(out.resolve())
    payload = dict(report)
    if out and not args.include_text:
        payload.pop("text", None)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
