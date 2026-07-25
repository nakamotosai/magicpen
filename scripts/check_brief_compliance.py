#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写后：内置可机检的 brief 合规项。

内置（自动从 brief 抽或 --flag 覆盖）：
  - 汉字量区间
  - 中文编号大标题 ## 一、/二、/三、
  - 独立空行金句条数
  - 破折号密度上限
  - AI 套话命中
  - 列表行密度
  - 显式禁词（brief「禁止X」或 --ban）

不在检查器内的条件 → 报告 manual_review[]，由 Judge/主控人工项勾。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

AI_TELLS = [
    r"综上所述",
    r"总而言之",
    r"值得注意的是",
    r"赋能",
    r"闭环",
    r"底层逻辑",
]


def han_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def parse_brief(brief: str) -> dict:
    spec: dict = {
        "min_han": None,
        "max_han": None,
        "require_h2_cn": False,
        "min_h2_cn": 0,
        "min_golden": 0,
        "max_dash_per_1k": None,
        "ban_words": [],
        "manual_hints": [],
    }
    # 约 1500 汉字 / 约1500字
    m = re.search(r"约\s*(\d{3,4})\s*汉?字", brief)
    if m:
        n = int(m.group(1))
        spec["min_han"] = int(n * 0.9)
        spec["max_han"] = int(n * 1.1)
    # 1400–1600 / 1400-1600 / 1400~1600
    m = re.search(r"(\d{3,4})\s*[-–—~～至到]\s*(\d{3,4})\s*汉?字?", brief)
    if m:
        spec["min_han"] = int(m.group(1))
        spec["max_han"] = int(m.group(2))
    # 三大块 / 三个标题 / ## 一、
    if re.search(r"三大块|三个.*标题|##\s*一、|编号的大标题|分三", brief):
        spec["require_h2_cn"] = True
        spec["min_h2_cn"] = 3
    m = re.search(r"至少\s*(\d+)\s*句.*金句|金句[^\n]{0,12}(\d+)", brief)
    if m:
        g = m.group(1) or m.group(2)
        if g:
            spec["min_golden"] = int(g)
    elif "金句" in brief:
        spec["min_golden"] = 3
        spec["manual_hints"].append("brief 提到金句但未写条数，默认 ≥3")
    if re.search(r"破折号\s*(尽量\s*)?0|禁止破折|破折号尽量", brief):
        spec["max_dash_per_1k"] = 0.5
    # 禁止 A/B/C
    for m in re.finditer(r"禁止[：:]\s*([^\n。]+)", brief):
        chunk = m.group(1)
        for part in re.split(r"[、，,/]|或", chunk):
            p = part.strip().strip("「」\"'")
            if 1 <= len(p) <= 12 and p not in ("角色仿写", "复述", "续写"):
                # 跳过长句
                if re.search(r"[是的了在]$", p) and len(p) > 4:
                    continue
                spec["ban_words"].append(p)
    for tok in ("猫", "咱家", "鱼干"):
        if re.search(rf"禁止[^\n]{{0,20}}{re.escape(tok)}|{re.escape(tok)}[^\n]{{0,8}}禁止", brief):
            if tok not in spec["ban_words"]:
                spec["ban_words"].append(tok)
    # 无法机检的提示
    if re.search(r"讽刺|嘲讽|锋利", brief):
        spec["manual_hints"].append("语气讽刺/锋利 → manual_review（Judge）")
    if re.search(r"更正式|口语|第一人称|无人称", brief):
        spec["manual_hints"].append("人称/语体细调 → manual_review")
    return spec


def count_golden_lines(text: str) -> list[str]:
    lines = text.splitlines()
    goldens = []
    for i, ln in enumerate(lines):
        if not ln.strip() or ln.strip().startswith("#"):
            continue
        prev_empty = i == 0 or not lines[i - 1].strip()
        next_empty = i == len(lines) - 1 or not lines[i + 1].strip()
        if not (prev_empty and next_empty):
            continue
        h = han_count(ln)
        if 8 <= h <= 60:
            goldens.append(ln.strip())
    return goldens


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None)
    ap.add_argument("--min-han", type=int, default=None)
    ap.add_argument("--max-han", type=int, default=None)
    ap.add_argument("--require-h2-cn", action="store_true")
    ap.add_argument("--min-h2-cn", type=int, default=None)
    ap.add_argument("--min-golden", type=int, default=None)
    ap.add_argument("--max-dash-per-1k", type=float, default=None)
    ap.add_argument("--ban", type=str, default="", help="comma-separated ban words")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    draft = args.draft.read_text(encoding="utf-8") if args.draft.exists() else ""
    brief = args.brief.read_text(encoding="utf-8") if args.brief and args.brief.exists() else ""
    spec = parse_brief(brief) if brief else {
        "min_han": None,
        "max_han": None,
        "require_h2_cn": False,
        "min_h2_cn": 0,
        "min_golden": 0,
        "max_dash_per_1k": None,
        "ban_words": [],
        "manual_hints": ["无 brief：仅跑显式 flag"],
    }

    if args.min_han is not None:
        spec["min_han"] = args.min_han
    if args.max_han is not None:
        spec["max_han"] = args.max_han
    if args.require_h2_cn:
        spec["require_h2_cn"] = True
        spec["min_h2_cn"] = args.min_h2_cn or spec["min_h2_cn"] or 3
    if args.min_h2_cn is not None:
        spec["min_h2_cn"] = args.min_h2_cn
        spec["require_h2_cn"] = True
    if args.min_golden is not None:
        spec["min_golden"] = args.min_golden
    if args.max_dash_per_1k is not None:
        spec["max_dash_per_1k"] = args.max_dash_per_1k
    if args.ban:
        for w in args.ban.split(","):
            w = w.strip()
            if w and w not in spec["ban_words"]:
                spec["ban_words"].append(w)

    checks = []
    han = han_count(draft)
    # han
    if spec["min_han"] is not None or spec["max_han"] is not None:
        lo = spec["min_han"] if spec["min_han"] is not None else 0
        hi = spec["max_han"] if spec["max_han"] is not None else 10**9
        ok = lo <= han <= hi
        checks.append({"id": "han_range", "ok": ok, "han": han, "min": lo, "max": hi})
    # h2 cn
    if spec["require_h2_cn"] or (spec["min_h2_cn"] or 0) > 0:
        titles = [ln.strip() for ln in draft.splitlines() if re.match(r"^##\s*[一二三四五六七八九十]、", ln)]
        need = spec["min_h2_cn"] or 3
        ok = len(titles) >= need
        has_seq = all(
            any(re.match(rf"^##\s*{c}、", t) for t in titles)
            for c in list("一二三")[: min(3, need)]
        )
        checks.append({
            "id": "h2_cn_numbered",
            "ok": ok and has_seq,
            "titles": titles,
            "need": need,
        })
    # golden
    if (spec["min_golden"] or 0) > 0:
        goldens = count_golden_lines(draft)
        ok = len(goldens) >= spec["min_golden"]
        checks.append({
            "id": "golden_lines",
            "ok": ok,
            "count": len(goldens),
            "need": spec["min_golden"],
            "samples": goldens[:5],
        })
    # dash
    if spec["max_dash_per_1k"] is not None:
        dashes = len(re.findall(r"[—–―]", draft))
        per = dashes / max(han, 1) * 1000
        ok = per <= spec["max_dash_per_1k"]
        checks.append({
            "id": "dash_per_1k",
            "ok": ok,
            "value": round(per, 3),
            "max": spec["max_dash_per_1k"],
        })
    # ban words
    if spec["ban_words"]:
        hits = {w: draft.count(w) for w in spec["ban_words"] if w in draft}
        checks.append({"id": "ban_words", "ok": len(hits) == 0, "hits": hits})
    # ai tells always soft-hard: fail if any
    ai_hits = []
    for pat in AI_TELLS:
        if re.search(pat, draft):
            ai_hits.append(pat)
    checks.append({"id": "ai_tells", "ok": len(ai_hits) == 0, "hits": ai_hits})
    # list density soft fail if >0.25 of nonempty lines look like lists
    lines = [ln for ln in draft.splitlines() if ln.strip()]
    listish = sum(1 for ln in lines if re.match(r"^\s*([-*•]|\d+[\.\)、])\s+", ln))
    ld = listish / max(len(lines), 1)
    checks.append({
        "id": "list_density",
        "ok": ld <= 0.25,
        "value": round(ld, 3),
        "max": 0.25,
    })

    hard_ok = all(c["ok"] for c in checks)
    report = {
        "ok": hard_ok,
        "han": han,
        "spec": spec,
        "checks": checks,
        "manual_review": spec.get("manual_hints") or [],
        "note": "未机检条件进 manual_review；由 Judge/主控勾",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if hard_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
