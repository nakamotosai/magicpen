#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装 Judge 提示词：rules + sample 摘要指针 + draft + brief + 闸结果。

Judge 分身只吃 JUDGE_PROMPT，输出 JUDGE_SCORE.json（见文末 schema）。
"""
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
    sample = load(sample_p)
    # sample 可长：全文仍给（Judge 要对照笔迹）；标注仅笔迹
    draft_t = load(draft)
    brief_t = load(brief) if brief else "（无 brief 文件）"
    gates_t = load(gates_json) if gates_json else "（无写后闸 JSON）"

    parts = []
    parts.append(f"# 卡卡西 · Judge 提示词（人格包 `{persona.name}`）\n\n")
    parts.append(
        "你是评分分身（Judge only）。**禁止改文件以外的业务逻辑**；"
        "只读下列材料，输出 **唯一一个 JSON 对象** 到约定路径（主控指定）。\n\n"
        "双轴：\n"
        "- **A 轴 fidelity**：是否像 sample+rules 的笔迹（句段、冷热、禁套话、换行）。\n"
        "- **B 轴 brief**：是否满足用户当次事实/结构/长度/语气（机检项已在写后闸）。\n"
        "- 硬分 score_vs_anchor 只是旁证，**不得单独 PASS 交付**。\n"
        "- **风格≠身份**：除非 brief 明文角色仿写，draft 出现样本身份壳 → A 轴 FAIL。\n\n"
    )
    parts.append("## 1. rules.md（全文）\n\n")
    parts.append(rules)
    parts.append("\n\n## 2. sample.md（仅笔迹对照）\n\n```text\n")
    parts.append(sample)
    parts.append("\n```\n\n## 3. brief（用户当次）\n\n")
    parts.append(brief_t)
    parts.append("\n\n## 4. draft（待评）\n\n```text\n")
    parts.append(draft_t)
    parts.append("\n```\n\n## 5. 写后机检闸（JSON，事实）\n\n```json\n")
    parts.append(gates_t if gates_t else "{}")
    parts.append("\n```\n\n")
    parts.append(
        "## 6. 输出 schema（只输出 JSON，无 Markdown 围栏）\n\n"
        "{\n"
        '  "pass": true,\n'
        '  "axis_a_fidelity": 0.0,\n'
        '  "axis_b_brief": 0.0,\n'
        '  "rules_compliance": 0.0,\n'
        '  "identity_ok": true,\n'
        '  "caricature_risk": false,\n'
        '  "manual_items": [{"item": "...", "ok": true, "note": "..."}],\n'
        '  "fail_reasons": [],\n'
        '  "rewrite_directives": [],\n'
        '  "one_line": "..."\n'
        "}\n\n"
        "规则：pass=true 当且仅当 identity_ok 且 axis_a≥0.7 且 axis_b≥0.7 "
        "且机检闸无硬失败（见第5节 ok 字段）。"
        "否则 pass=false，并填 rewrite_directives 给 Writer 下一轮。\n"
    )
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None)
    ap.add_argument("--gates", type=Path, default=None, help="post_write_gates JSON")
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
