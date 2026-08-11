#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""写后一键机检：身份串味 + brief 合规 + 硬分旁证 → 合并 JSON。

主控/编排在 Writer 落 draft 后必跑；exit0 仅表示机检过，交付还要 dual_axis_gate + Judge。
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path


def run_py(script: Path, args: list[str]) -> tuple[int, dict]:
    cmd = [sys.executable, str(script), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    try:
        data = json.loads(p.stdout)
    except json.JSONDecodeError:
        data = {"ok": False, "error": "parse_fail", "stdout": p.stdout, "stderr": p.stderr}
    return p.returncode, data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--brief", type=Path, default=None)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--skip-hard", action="store_true")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent

    # 空/缺 draft 直接硬失败（防四闸空串兜底全绿）
    han_draft = 0
    if args.draft.exists():
        t = args.draft.read_text(encoding="utf-8", errors="replace")
        han_draft = len(re.findall(r"[一-鿿]", t))
    if han_draft < 1:
        report = {
            "ok": False,
            "gates": [],
            "error": "draft_empty_or_missing",
            "draft_han": han_draft,
            "note": "draft 无正文，机检不适用，禁止空稿放行",
        }
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    gates = []

    # identity
    code_i, data_i = run_py(
        root / "assert_identity_bleed.py",
        [
            "--persona",
            str(args.persona),
            "--draft",
            str(args.draft),
            *(["--brief", str(args.brief)] if args.brief else []),
        ],
    )
    gates.append({"name": "identity", "exit": code_i, "ok": data_i.get("ok", False), "detail": data_i})

    # content bleed (sample events / 富士山问题)
    code_c, data_c = run_py(
        root / "assert_content_bleed.py",
        [
            "--persona",
            str(args.persona),
            "--draft",
            str(args.draft),
            *(["--brief", str(args.brief)] if args.brief else []),
        ],
    )
    gates.append({"name": "content_bleed", "exit": code_c, "ok": data_c.get("ok", False), "detail": data_c})

    # brief compliance
    code_b, data_b = run_py(
        root / "check_brief_compliance.py",
        [
            "--draft",
            str(args.draft),
            *(["--brief", str(args.brief)] if args.brief else []),
        ],
    )
    gates.append({"name": "brief_compliance", "exit": code_b, "ok": data_b.get("ok", False), "detail": data_b})

    # v3.5 中段场面/查证（分节文）
    code_s, data_s = run_py(
        root / "assert_section_scene.py",
        [
            "--draft",
            str(args.draft),
            *(["--brief", str(args.brief)] if args.brief else []),
        ],
    )
    gates.append({"name": "section_scene", "exit": code_s, "ok": data_s.get("ok", False), "detail": data_s})

    # hard score
    data_h = {}
    code_h = 0
    if not args.skip_hard and (args.persona / "metrics.json").exists():
        code_h, data_h = run_py(
            root / "score_loop.py",
            ["--persona", str(args.persona), "--draft", str(args.draft)],
        )
        gates.append({
            "name": "hard_score",
            "exit": code_h,
            "ok": data_h.get("ok", False),
            "detail": {"score_vs_anchor": data_h.get("score_vs_anchor"), "tier_hint": data_h.get("tier_hint")},
            "side_only": True,
        })
    else:
        gates.append({"name": "hard_score", "ok": True, "skipped": True, "side_only": True})

    # 机检硬失败：identity + content_bleed + brief + section_scene；hard 不否决 ok
    hard_fail = any(
        g["name"] in ("identity", "content_bleed", "brief_compliance", "section_scene")
        and not g.get("ok")
        for g in gates
    )
    report = {
        "ok": not hard_fail,
        "gates": gates,
        "identity": data_i,
        "content_bleed": data_c,
        "brief_compliance": data_b,
        "section_scene": data_s,
        "hard": data_h,
        "manual_review": data_b.get("manual_review") or [],
        "note": "ok=机检硬闸(含内容串戏+中段场面)；交付还须 Judge(含灵魂轴) + dual_axis_gate",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
