#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Install facade：原文 → 人格包入库。

  pythonw run_install.py --raw RAW.md --id laocai [--calibrate] [--out DIR]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

from persona_lib import DEFAULT_LIB, lib_persona_dir, sanitize_id, utc_now, write_persona_meta

ROOT = Path(__file__).resolve().parent


def run(script: str, args: list[str]) -> tuple[int, str]:
    cmd = [sys.executable, str(ROOT / script), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    out = (p.stdout or "") + (p.stderr or "")
    return p.returncode, out


def han_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def calibrate_rules(persona: Path, qc: dict) -> str | None:
    """布局极端时给 rules 头加校准注；必要时改第 5 条语气（短行合法）。"""
    rules_p = persona / "rules.md"
    if not rules_p.exists():
        return None
    ssl = float(qc.get("sample_short_line_ratio") or 0)
    layout = qc.get("layout_score")
    if ssl < 0.55 and (layout is None or float(layout) >= 0.7):
        return None
    text = rules_p.read_text(encoding="utf-8")
    note = (
        "\n> **校准**：样本短行/碎段偏多（short_line_ratio="
        f"{ssl}）。仿写须保留空行与短段指纹，禁止强行合成无空行大段墙。\n"
    )
    if "校准" not in text[:400]:
        # 插在标题后
        parts = text.split("\n", 3)
        if len(parts) >= 3:
            text = "\n".join(parts[:3]) + note + (parts[3] if len(parts) > 3 else "")
        else:
            text = note + text
    # 弱化「禁止一行一句」若样本本就短
    if ssl >= 0.55:
        text = text.replace(
            "禁止一行一句铺满全篇；多句应落在同一段落里，换行跟样本段落节奏。",
            "样本短行/单句成段偏多；仿写跟样本换行与空行密度，禁止抹成无空行散文墙。",
        )
    rules_p.write_text(text, encoding="utf-8")
    return "layout_calibrated"


def main() -> int:
    ap = argparse.ArgumentParser(description="magicpen Install：原文→人格包")
    ap.add_argument("--raw", type=Path, required=True, help="原文路径")
    ap.add_argument("--id", type=str, required=True, help="人格 id")
    ap.add_argument("--out", type=Path, default=None, help="默认 ~/.omp/magicpen/personas/<id>")
    ap.add_argument("--target", type=int, default=2000)
    ap.add_argument("--calibrate", action="store_true", help="布局极端时校准 rules")
    ap.add_argument("--display-name", type=str, default="")
    args = ap.parse_args()

    if not args.raw.exists():
        print(json.dumps({"ok": False, "error": f"raw missing: {args.raw}"}, ensure_ascii=False))
        return 2

    pid = sanitize_id(args.id)
    persona = args.out.resolve() if args.out else lib_persona_dir(pid)
    persona.mkdir(parents=True, exist_ok=True)

    raw_text = args.raw.read_text(encoding="utf-8")
    raw_han = han_count(raw_text)

    sample_out = persona / "sample.md"
    # cut if needed
    if raw_han > 3000 or (raw_han > args.target and raw_han >= 500):
        code, out = run(
            "cut_train_window.py",
            [
                "--sample",
                str(args.raw),
                "--out",
                str(sample_out),
                "--target",
                str(args.target),
                "--min",
                "500",
                "--max",
                "3000",
            ],
        )
        if code != 0 and not sample_out.exists():
            # fallback copy head
            sample_out.write_text(raw_text, encoding="utf-8")
    else:
        shutil.copy2(args.raw, sample_out) if args.raw.resolve() != sample_out.resolve() else None
        if not sample_out.exists():
            sample_out.write_text(raw_text, encoding="utf-8")

    code, out = run(
        "style_sensors.py",
        [
            "--text",
            str(sample_out),
            "--rules",
            str(persona / "rules.md"),
            "--metrics",
            str(persona / "metrics.json"),
        ],
    )
    if code != 0:
        print(json.dumps({"ok": False, "error": "style_sensors failed", "log": out[-2000:]}, ensure_ascii=False))
        return 1

    # v3.4：思维链 + 内容禁表（灵魂层）
    code_m, out_m = run(
        "extract_mind_and_bans.py",
        ["--persona", str(persona)],
    )
    if code_m != 0:
        print(json.dumps({"ok": False, "error": "extract_mind_and_bans failed", "log": out_m[-1500:]}, ensure_ascii=False))
        return 1

    code, qc_out = run("quality_check.py", ["--persona", str(persona)])
    try:
        qc = json.loads(qc_out[qc_out.find("{") : qc_out.rfind("}") + 1])
    except Exception:
        qc = {"ok": code == 0, "raw": qc_out[-500:]}

    cal = None
    if args.calibrate:
        cal = calibrate_rules(persona, qc if isinstance(qc, dict) else {})

    write_persona_meta(
        persona,
        {
            "id": pid,
            "display_name": args.display_name or pid,
            "sample_han": (qc or {}).get("sample_han"),
            "layout_score": (qc or {}).get("layout_score"),
            "calibrated": bool(cal),
            "layout_note": cal,
            "created_at": utc_now(),
            "source_raw": str(args.raw.resolve()),
            "lib": str(DEFAULT_LIB),
        },
    )

    report = {
        "ok": bool(qc.get("ok", code == 0)) if isinstance(qc, dict) else code == 0,
        "action": "install",
        "persona": str(persona),
        "id": pid,
        "quality_check": qc,
        "calibrated": cal,
        "next": "Write: pythonw scripts/run_write.py --persona "
        + pid
        + " --brief BRIEF.md  （或主控派 Writer 前 --stage prepare）",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
