#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装 Judge 提示词 v3.4：三轴 A笔迹 / B brief / C灵魂(思维链+反同构+反串戏)。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def load(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip() if p.exists() else ""


def build(
    persona: Path,
    draft: Path,
    brief: Path | None,
    gates_json: Path | None,
) -> str:
    sample_p = persona / "sample.md"
    if not sample_p.exists():
        sample_p = persona / "train.md"
    rules = load(persona / "rules.md")
    mind = load(persona / "mind.md")
    sample = load(sample_p)
    draft_t = load(draft)
    brief_t = load(brief) if brief else "（无 brief 文件）"
    gates_t = load(gates_json) if gates_json else "（无写后闸 JSON）"
    cban = load(persona / "content_ban.txt")

    parts = []
    parts.append(f"# 神笔 · Judge 提示词 v3.4（人格包 `{persona.name}`）\n\n")
    parts.append(
        "你是评分分身（Judge only）。只读材料，输出 **唯一 JSON**。\n\n"
        "## 三轴（缺一不可）\n"
        "- **A 笔迹 fidelity**：空行/段句/口气/禁套话是否像 sample+rules 的 **P0/P1**（不是只看平均句长）。\n"
        "- **B brief**：当次事实/结构/长度是否满足。\n"
        "- **C 灵魂 soul**（v3.4 新增，**权重最高之一**）：\n"
        "  1) 是否按 mind 的「怎么想」推进（刺激→查证/场面→反差→判断→短收），而不是通用议论文骨架；\n"
        "  2) 读起来是否像**这个人**，而不是鲁迅腔/网文腔/AI 政论；\n"
        "  3) 有无复读 sample 事件或 content_ban；\n"
        "  4) 开篇/主隐喻/节末是否像模板复读（「不是草包所以更可怕」「最怕的是…」刷屏→扣分）。\n"
        "- 硬分 score_vs_anchor 只旁证。\n"
        "- **机检绿 ≠ 像**。若 A/B 高但 C 低 → **pass=false**。\n\n"
    )
    if mind:
        parts.append("## 0. mind.md（思维链 · 灵魂参照）\n\n")
        parts.append(mind)
        parts.append("\n\n")
    parts.append("## 1. rules.md（加权）\n\n")
    parts.append(rules)
    parts.append("\n\n## 2. content_ban\n\n")
    parts.append(cban or "（无）")
    parts.append("\n\n## 3. sample.md（仅笔迹对照，可截读）\n\n```text\n")
    parts.append(sample[:4000])
    parts.append("\n```\n\n## 4. brief\n\n")
    parts.append(brief_t)
    parts.append("\n\n## 5. draft\n\n```text\n")
    parts.append(draft_t)
    parts.append("\n```\n\n## 6. 写后机检闸\n\n```json\n")
    parts.append(gates_t if gates_t else "{}")
    parts.append(
        "\n```\n\n"
        "> **机检优先**：汉字区间、H2 编号、content_bleed、identity 以本节 JSON 为准。"
        "若 `brief_compliance.checks` 里 `han_range.ok=true`，**禁止**再以「字数不足」否决 axis_b；"
        "axis_b 只评事实/结构/角度是否覆盖 brief。\n\n"
    )
    parts.append(
        "## 7. 输出 schema（只输出 JSON，无 Markdown 围栏）\n\n"
        "{\n"
        '  "pass": true,\n'
        '  "axis_a_fidelity": 0.0,\n'
        '  "axis_b_brief": 0.0,\n'
        '  "axis_c_soul": 0.0,\n'
        '  "rules_compliance": 0.0,\n'
        '  "identity_ok": true,\n'
        '  "content_ok": true,\n'
        '  "caricature_risk": false,\n'
        '  "templatey_risk": false,\n'
        '  "sounds_like_other_persona": null,\n'
        '  "manual_items": [{"item": "...", "ok": true, "note": "..."}],\n'
        '  "fail_reasons": [],\n'
        '  "rewrite_directives": [],\n'
        '  "one_line": "..."\n'
        "}\n\n"
        "规则：pass=true 当且仅当 identity_ok 且 content_ok 且 "
        "axis_a≥0.7 且 axis_b≥0.7 且 **axis_c_soul≥0.72** "
        "且机检闸无硬失败。\n"
        "若读起来更像鲁迅/网文/AI 政论而不是本人格 → axis_c 必须 <0.7 且 pass=false，"
        "rewrite_directives 写清要回到 mind 的哪一步。\n"
    )
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None)
    ap.add_argument("--gates", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    args = ap.parse_args()
    try:
        text = build(args.persona.resolve(), args.draft, args.brief, args.gates)
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(json.dumps({"ok": True, "out": str(args.out), "chars": len(text)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
