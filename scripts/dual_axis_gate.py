#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""双轴自动化收口：硬分旁证 + Judge JSON + 写后机检 → deliver_ok。

硬分永不单独放行。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def loadj(p: Path | None) -> dict:
    if not p or not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hard", type=Path, help="score_loop 输出 JSON")
    ap.add_argument("--judge", type=Path, help="JUDGE_SCORE.json")
    ap.add_argument("--gates", type=Path, help="post_write_gates / 合并闸 JSON")
    ap.add_argument("--hard-min", type=float, default=0.45, help="硬分旁证下限（不单独决定）")
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()

    hard = loadj(args.hard)
    judge = loadj(args.judge)
    gates = loadj(args.gates)

    if args.gates is None or not args.gates.exists():
        report = {
            "deliver_ok": False,
            "ok": False,
            "gates_ok": False,
            "identity_ok": False,
            "content_ok": False,
            "section_ok": False,
            "judge_pass": False,
            "axis_a_fidelity": None,
            "axis_b_brief": None,
            "axis_c_soul": None,
            "reasons": ["gates_missing"],
            "warnings": [],
            "rewrite_directives": [],
            "note": "gates 文件缺失，fail-closed",
        }
        text = json.dumps(report, ensure_ascii=False, indent=2)
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(text, encoding="utf-8")
        print(text)
        return 1

    hard_score = hard.get("score_vs_anchor")
    if hard_score is None and isinstance(hard.get("summary"), dict):
        hard_score = hard["summary"].get("score_vs_anchor")

    gates_ok = gates.get("ok", True) if gates else True
    identity_ok = True
    if gates:
        for g in gates.get("gates", []) if isinstance(gates.get("gates"), list) else []:
            if g.get("name") == "identity" and g.get("ok") is False:
                identity_ok = False
        if "identity" in gates and isinstance(gates["identity"], dict):
            identity_ok = bool(gates["identity"].get("ok", True))

    judge_pass = bool(judge.get("pass")) if judge else False
    axis_a = float(judge.get("axis_a_fidelity") or 0)
    axis_b = float(judge.get("axis_b_brief") or 0)
    # v3.4：缺 axis_c_soul 字段 = 灵魂未评，按 0 处理（禁假绿）
    has_axis_c = bool(judge) and ("axis_c_soul" in judge)
    axis_c = float(judge.get("axis_c_soul") or 0) if judge else 0.0
    if judge and "identity_ok" in judge:
        identity_ok = identity_ok and bool(judge["identity_ok"])
    content_ok = True
    if gates:
        for g in gates.get("gates", []) if isinstance(gates.get("gates"), list) else []:
            if g.get("name") == "content_bleed" and g.get("ok") is False:
                content_ok = False
        if "content_bleed" in gates and isinstance(gates["content_bleed"], dict):
            content_ok = content_ok and bool(gates["content_bleed"].get("ok", True))
    if judge and "content_ok" in judge:
        content_ok = content_ok and bool(judge["content_ok"])
    section_ok = True
    if gates:
        for g in gates.get("gates", []) if isinstance(gates.get("gates"), list) else []:
            if g.get("name") == "section_scene" and g.get("ok") is False:
                section_ok = False
        if "section_scene" in gates and isinstance(gates["section_scene"], dict):
            section_ok = section_ok and bool(gates["section_scene"].get("ok", True))

    hard_side_ok = hard_score is None or float(hard_score) >= args.hard_min

    # v3.4/3.5：A/B/C 三轴；C 灵魂不足或缺失不得交付（即使机检全绿）
    reasons = []
    if not gates_ok:
        reasons.append("gates_failed")
    if not identity_ok:
        reasons.append("identity_bleed")
    if not content_ok:
        reasons.append("content_bleed")
    if not section_ok:
        reasons.append("section_scene_fail")
    if not judge:
        reasons.append("judge_missing")
    elif not has_axis_c:
        reasons.append("axis_c_soul_missing")
        judge_pass = False
    elif not judge_pass:
        reasons.append("judge_fail")
        if axis_a < 0.7:
            reasons.append("axis_a_low")
        if axis_b < 0.7:
            reasons.append("axis_b_low")
        if axis_c < 0.72:
            reasons.append("axis_c_soul_low")
    elif axis_c < 0.72:
        reasons.append("axis_c_soul_low")
        judge_pass = False

    deliver_ok = (
        gates_ok
        and identity_ok
        and content_ok
        and section_ok
        and judge_pass
        and bool(judge)
        and has_axis_c
        and axis_c >= 0.72
    )
    warnings = []
    if hard_score is not None and float(hard_score) < args.hard_min:
        warnings.append(f"hard_score {hard_score} < {args.hard_min} (旁证偏低，不单独否决)")
    if not hard_side_ok and deliver_ok:
        warnings.append("deliver_with_low_hard_proxy")
    if judge and judge.get("templatey_risk"):
        warnings.append("templatey_risk")
    if judge and judge.get("sounds_like_other_persona"):
        warnings.append(f"sounds_like:{judge.get('sounds_like_other_persona')}")

    report = {
        "deliver_ok": deliver_ok,
        "ok": deliver_ok,
        "hard_score": hard_score,
        "hard_side_ok": hard_side_ok,
        "gates_ok": gates_ok,
        "identity_ok": identity_ok,
        "content_ok": content_ok,
        "section_ok": section_ok,
        "judge_pass": judge_pass,
        "axis_a_fidelity": axis_a if judge else None,
        "axis_b_brief": axis_b if judge else None,
        "axis_c_soul": axis_c if judge else None,
        "reasons": reasons,
        "warnings": warnings,
        "rewrite_directives": judge.get("rewrite_directives") if judge else [],
        "note": "三轴：A笔迹 B=brief C=灵魂；硬分旁证；机检含内容串戏；绿≠像",
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if deliver_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
