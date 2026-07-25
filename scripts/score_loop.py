#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""对 draft 跑传感器并对照 persona/metrics.json；硬分旁证。"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--metrics", type=Path, help="default: persona/metrics.json")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--voice", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.voice is not None:
        print(json.dumps({"ok": False, "error": "removed: use --persona"}, ensure_ascii=False))
        return 2

    root = Path(__file__).resolve().parent
    sensors = root / "style_sensors.py"
    metrics = args.metrics or (args.persona / "metrics.json")
    if not metrics.exists():
        print(json.dumps({"ok": False, "error": f"metrics missing: {metrics}"}, ensure_ascii=False))
        return 1
    if not args.draft.exists():
        print(json.dumps({"ok": False, "error": f"draft missing: {args.draft}"}, ensure_ascii=False))
        return 1

    draft_metrics = args.persona / "runs" / "_last_draft_metrics.json"
    draft_metrics.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        str(sensors),
        "--text",
        str(args.draft),
        "--min-chars",
        "50",
        "--metrics",
        str(draft_metrics),
        "--metrics-ref",
        str(metrics),
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    try:
        summary = json.loads(p.stdout)
    except json.JSONDecodeError:
        summary = {"error": "parse_fail", "stdout": p.stdout, "stderr": p.stderr}

    score = summary.get("score_vs_anchor")
    report = {
        "ok": p.returncode == 0 and score is not None,
        "score_vs_anchor": score,
        "tier_hint": (
            "A_hard_proxy" if score is not None and score >= 0.85 else
            "B_hard_proxy" if score is not None and score >= 0.70 else
            "C_or_below"
        ),
        "note": "硬分旁证；主裁判是 Judge 对照 rules.md + 原文",
        "summary": summary,
        "persona": str(args.persona),
        "draft": str(args.draft),
        "metrics_ref": str(metrics),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
    print(text)
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
