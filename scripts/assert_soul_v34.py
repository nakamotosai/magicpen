#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Kill：神笔 v3.4/v3.5 灵魂层接线（mind/content_ban/三轴/扩写/中段场面）。

  pythonw assert_soul_v34.py
  exit 0 = 接线齐；非 0 = 缺表面
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SKILL = ROOT.parent
PERSONA_DEMO = Path.home() / ".omp" / "magicpen" / "personas" / "laocai"


def must_contain(path: Path, needles: list[str], label: str, errors: list[str]) -> None:
    if not path.exists():
        errors.append(f"missing {label}: {path}")
        return
    t = path.read_text(encoding="utf-8", errors="replace")
    for n in needles:
        if n not in t:
            errors.append(f"{label} missing `{n}`: {path.name}")


def main() -> int:
    errors: list[str] = []

    # scripts exist
    for name in (
        "extract_mind_and_bans.py",
        "assert_content_bleed.py",
        "assert_section_scene.py",
        "build_write_prompt.py",
        "build_judge_prompt.py",
        "dual_axis_gate.py",
        "run_writer_llm.py",
        "run_judge_llm.py",
        "style_sensors.py",
        "check_brief_compliance.py",
        "run_install.py",
        "post_write_gates.py",
    ):
        if not (ROOT / name).exists():
            errors.append(f"missing script {name}")

    must_contain(
        ROOT / "build_write_prompt.py",
        ["mind.md", "content_ban", "random_slot", "v3.5", "no_sample"],
        "build_write_prompt",
        errors,
    )
    must_contain(
        ROOT / "assert_section_scene.py",
        ["section_scene", "SCENE_PAT"],
        "assert_section_scene",
        errors,
    )
    must_contain(
        ROOT / "post_write_gates.py",
        ["section_scene", "assert_section_scene"],
        "post_write_gates",
        errors,
    )
    must_contain(
        ROOT / "run_writer_llm.py",
        ["mind_rewrite", "section_scene_ok", "strip_em_dashes", "dash_stripped"],
        "run_writer_llm",
        errors,
    )
    brief_tpl = SKILL / "references" / "brief-longform-v35.md"
    if not brief_tpl.exists():
        errors.append("missing references/brief-longform-v35.md")
    must_contain(
        ROOT / "build_judge_prompt.py",
        ["axis_c_soul", "0.72", "v3.4"],
        "build_judge_prompt",
        errors,
    )
    must_contain(
        ROOT / "dual_axis_gate.py",
        ["axis_c_soul", "0.72", "content_ok"],
        "dual_axis_gate",
        errors,
    )
    must_contain(
        ROOT / "run_writer_llm.py",
        ["brief_min", "auto_expanded", "## \\1"],
        "run_writer_llm",
        errors,
    )
    must_contain(
        ROOT / "run_judge_llm.py",
        ["axis_c_soul", "0.72"],
        "run_judge_llm",
        errors,
    )
    must_contain(
        ROOT / "style_sensors.py",
        ["0.6.0-soul", "P0", "rules_md_lines"],
        "style_sensors",
        errors,
    )
    must_contain(
        ROOT / "run_install.py",
        ["extract_mind_and_bans"],
        "run_install",
        errors,
    )
    must_contain(
        ROOT / "check_brief_compliance.py",
        ["一二三四五六七八九十", "h2_cn_numbered"],
        "check_brief_compliance",
        errors,
    )

    skill_md = SKILL / "SKILL.md"
    if skill_md.exists():
        sm = skill_md.read_text(encoding="utf-8", errors="replace")
        for n in ("mind.md", "content_ban", "axis_c", "v3.4", "灵魂"):
            if n not in sm:
                errors.append(f"SKILL.md missing `{n}`")
    else:
        errors.append("missing SKILL.md")

    # laocai demo persona soul files (if installed)
    if PERSONA_DEMO.is_dir():
        for f in ("mind.md", "content_ban.txt", "rules.md"):
            if not (PERSONA_DEMO / f).exists():
                errors.append(f"laocai persona missing {f}")
        rules = (PERSONA_DEMO / "rules.md").read_text(encoding="utf-8", errors="replace") if (PERSONA_DEMO / "rules.md").exists() else ""
        if rules and "P0" not in rules and "人工校准" not in rules:
            errors.append("laocai rules.md missing P0 weights (or 人工校准 marker)")

    ok = len(errors) == 0
    print(
        __import__("json").dumps(
            {"ok": ok, "gate": "assert_soul_v34", "errors": errors, "error_count": len(errors)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
