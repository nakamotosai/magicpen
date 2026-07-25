#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查人格包：sample.md + rules.md；字数硬底 500 / 硬顶 3000。

短行比/段均只进 **打分与 warnings**，不硬失败（原文可以是全短行）。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def han_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def layout_soft_score(short_line_ratio: float, mean_para_han: float) -> float:
    """0–1 旁证分；短行多不否决，只降分。"""
    # 短行：0.7 以上开始扣，1.0 仍给 0.35 底
    if short_line_ratio <= 0.45:
        s_short = 1.0
    elif short_line_ratio >= 1.0:
        s_short = 0.35
    else:
        s_short = 1.0 - (short_line_ratio - 0.45) / 0.55 * 0.65
    # 段均：极短段提示「碎」，但不否决
    if mean_para_han >= 60:
        s_para = 1.0
    elif mean_para_han >= 25:
        s_para = 0.55 + (mean_para_han - 25) / 35 * 0.45
    else:
        s_para = 0.4
    return round(0.55 * s_short + 0.45 * s_para, 3)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--voice", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.voice is not None:
        print(json.dumps({"ok": False, "error": "removed: use --persona only"}, ensure_ascii=False))
        return 2

    root = args.persona
    report: dict = {
        "persona": str(root),
        "ok": True,
        "errors": [],
        "warnings": [],
        "layout_score": None,
        "note": "短行/段均只打分不硬拦；硬失败仅缺文件/字数越界",
    }

    if not root.is_dir():
        report["ok"] = False
        report["errors"].append("path not a directory")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    sample_path = root / "sample.md"
    if not sample_path.exists() and (root / "train.md").exists():
        sample_path = root / "train.md"
        report["warnings"].append("using train.md as sample.md alias")
    if not sample_path.exists():
        report["ok"] = False
        report["errors"].append("missing sample.md")

    rules_path = root / "rules.md"
    if not rules_path.exists():
        report["ok"] = False
        report["errors"].append("missing rules.md")
    else:
        rt = rules_path.read_text(encoding="utf-8")
        numbered = re.findall(r"^\s*\d+\.\s+\S", rt, flags=re.M)
        report["rules_lines"] = len(numbered)
        if len(numbered) < 10:
            report["warnings"].append(f"rules.md only {len(numbered)} numbered lines; expect ~20")
        if "anchor.json" in rt:
            report["warnings"].append("rules.md unexpectedly mentions anchor.json")

    for legacy in ("anchor.json", "HARD_ANCHORS.md", "STYLE.md", "knobs.yaml", "SKILL.md"):
        if (root / legacy).exists():
            report["warnings"].append(f"legacy file (可删): {legacy}")

    if sample_path.exists():
        st = sample_path.read_text(encoding="utf-8").strip()
        han = han_count(st)
        report["sample_han"] = han
        if han < 500:
            report["ok"] = False
            report["errors"].append(f"sample han {han} < 500 floor")
        if han > 3000:
            report["ok"] = False
            report["errors"].append(f"sample han {han} > 3000 hard cap; cut first")
        paras = [p.strip() for p in re.split(r"\n\s*\n", st) if p.strip()]
        lines = [ln.strip() for ln in st.splitlines() if ln.strip()]
        mean_para = 0.0
        ssl = 0.0
        if paras:
            mean_para = sum(han_count(p) for p in paras) / len(paras)
            report["sample_mean_para_han"] = round(mean_para, 1)
            if mean_para < 40 and han >= 200:
                report["warnings"].append(
                    "mean paragraph <40 han（布局旁证偏低；原文可短行，rules 须人工贴样本）"
                )
        if lines:
            short_lines = sum(1 for ln in lines if han_count(ln) <= 25)
            ssl = short_lines / len(lines)
            report["sample_short_line_ratio"] = round(ssl, 3)
            if ssl > 0.7 and han >= 200:
                report["warnings"].append(
                    f"short_line_ratio {ssl:.2f} >0.7（仅打分；不硬失败；短行原文合法）"
                )
        if han >= 200 and (paras or lines):
            report["layout_score"] = layout_soft_score(ssl, mean_para)

    if (root / "metrics.json").exists():
        report["metrics"] = "present"
    else:
        report["warnings"].append("metrics.json optional missing (hard-score side channel)")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
