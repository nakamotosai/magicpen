#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成交付回执 RECEIPT.json + RECEIPT.md（护城河可见物）。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def loadj(p: Path | None) -> dict:
    if not p or not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def han_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None)
    ap.add_argument("--gates", type=Path, default=None)
    ap.add_argument("--deliver", type=Path, default=None)
    ap.add_argument("--judge", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--gates-only", action="store_true")
    args = ap.parse_args()

    draft_t = args.draft.read_text(encoding="utf-8") if args.draft.exists() else ""
    gates = loadj(args.gates)
    deliver = loadj(args.deliver)
    judge = loadj(args.judge)

    if deliver:
        deliver_ok = bool(deliver.get("deliver_ok"))
    elif gates:
        deliver_ok = bool(gates.get("ok"))
    else:
        deliver_ok = False

    checks = []
    bc = gates.get("brief_compliance") or {}
    for c in bc.get("checks") or []:
        checks.append(c)
    identity = gates.get("identity") or {}
    hard = gates.get("hard") or {}

    receipt = {
        "product": "magicpen",
        "version": "3.3",
        "persona": str(args.persona),
        "draft": str(args.draft),
        "brief": str(args.brief) if args.brief else None,
        "deliver_ok": deliver_ok,
        "gates_only": bool(args.gates_only),
        "han": han_count(draft_t),
        "identity_ok": identity.get("ok", True) if identity else True,
        "identity_hits": identity.get("hits") or [],
        "gates_ok": gates.get("ok"),
        "brief_checks": checks,
        "manual_review": gates.get("manual_review") or bc.get("manual_review") or [],
        "hard_score": hard.get("score_vs_anchor")
        if isinstance(hard, dict)
        else deliver.get("hard_score"),
        "judge_pass": judge.get("pass") if judge else deliver.get("judge_pass"),
        "axis_a_fidelity": judge.get("axis_a_fidelity")
        if judge
        else deliver.get("axis_a_fidelity"),
        "axis_b_brief": judge.get("axis_b_brief") if judge else deliver.get("axis_b_brief"),
        "rewrite_directives": (judge.get("rewrite_directives") if judge else None)
        or deliver.get("rewrite_directives")
        or [],
        "one_line": (judge.get("one_line") if judge else None)
        or ("机检通过（gates-only）" if args.gates_only and deliver_ok else ""),
        "note": "缺 RECEIPT = 未交付；网页仿写无此回执",
    }

    args.out_dir.mkdir(parents=True, exist_ok=True)
    jp = args.out_dir / "RECEIPT.json"
    jp.write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8")

    lines = [
        "# 神笔 · 验收回执 RECEIPT",
        "",
        f"- **可交付**：{'是' if receipt['deliver_ok'] else '否'}",
        f"- **人格包**：`{args.persona}`",
        f"- **汉字约**：{receipt['han']}",
        f"- **身份闸**：{'过' if receipt['identity_ok'] else '失败 ' + str(receipt['identity_hits'])}",
        f"- **机检 gates**：{'过' if receipt['gates_ok'] else '失败'}",
        f"- **模式**：{'gates-only（快路径）' if args.gates_only else '双轴 Judge+机检'}",
    ]
    if receipt.get("hard_score") is not None:
        lines.append(f"- **硬分旁证**：{receipt['hard_score']}（不单独定生死）")
    if receipt.get("judge_pass") is not None:
        lines.append(f"- **Judge pass**：{receipt['judge_pass']}")
    if receipt.get("axis_a_fidelity") is not None:
        lines.append(
            f"- **A 保真 / B brief**：{receipt.get('axis_a_fidelity')} / {receipt.get('axis_b_brief')}"
        )
    if checks:
        lines.append("")
        lines.append("## brief 机检")
        for c in checks:
            mark = "OK" if c.get("ok") else "FAIL"
            lines.append(f"- [{mark}] `{c.get('id')}`")
    manual = receipt.get("manual_review") or []
    if manual:
        lines.append("")
        lines.append("## 须人工/Judge 项")
        for m in manual:
            lines.append(f"- {m}")
    dirs = receipt.get("rewrite_directives") or []
    if dirs:
        lines.append("")
        lines.append("## 下一刀（回炉）")
        for d in dirs:
            lines.append(f"- {d}")
    if receipt.get("one_line"):
        lines.append("")
        lines.append(f"> {receipt['one_line']}")
    lines.append("")
    mp = args.out_dir / "RECEIPT.md"
    mp.write_text("\n".join(lines), encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "deliver_ok": deliver_ok,
                "receipt_json": str(jp),
                "receipt_md": str(mp),
            },
            ensure_ascii=False,
        )
    )
    return 0 if deliver_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
