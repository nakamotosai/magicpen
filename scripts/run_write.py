#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Write facade：人格包 + brief → 编排写稿/闸/回执。

阶段（Agent 产线）：
  prepare  — loop + WRITE_PROMPT + ORCHESTRATE(writer)
  post     — 要求 draft 已在；GATES + JUDGE_PROMPT 或 gates-only
  finalize — dual_axis + RECEIPT + loop record + hygiene
  auto     — prepare；若 draft 已存在则 post+finalize（无分身时用已有 draft 测闸）

  pythonw run_write.py --persona ID|PATH --brief B.md --stage prepare
  # Writer 分身写 draft.md
  pythonw run_write.py --persona ... --brief B.md --stage post
  # Judge 分身写 JUDGE_SCORE.json（非 --gates-only）
  pythonw run_write.py --persona ... --brief B.md --stage finalize
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from persona_lib import resolve_persona

ROOT = Path(__file__).resolve().parent


def run(script: str, args: list[str]) -> tuple[int, dict | str]:
    cmd = [sys.executable, str(ROOT / script), *args]
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    text = p.stdout or ""
    try:
        start = text.find("{")
        end = text.rfind("}") + 1
        data = json.loads(text[start:end]) if start >= 0 else {"raw": text, "stderr": p.stderr}
    except json.JSONDecodeError:
        data = {"raw": text, "stderr": p.stderr, "ok": p.returncode == 0}
    return p.returncode, data


def next_run_id(persona: Path) -> str:
    runs = persona / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    n = 1
    while (runs / f"r{n}").exists():
        n += 1
    return f"r{n}"


def stage_prepare(persona: Path, brief: Path, run_id: str, max_loops: int) -> dict:
    run_dir = persona / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    # copy brief
    dest_brief = run_dir / "brief.md"
    dest_brief.write_text(brief.read_text(encoding="utf-8"), encoding="utf-8")

    # loop init if needed
    ls = persona / "runs" / "loop_state.json"
    if not ls.exists() or json.loads(ls.read_text(encoding="utf-8")).get("status") in (
        "passed",
        "exhausted",
        "aborted",
        "idle",
    ):
        run("loop_state.py", ["--persona", str(persona), "init", "--max-loops", str(max_loops)])

    code, can = run("loop_state.py", ["--persona", str(persona), "can-write"])
    if code != 0:
        return {"ok": False, "error": "loop exhausted or blocked", "can_write": can}

    wp = run_dir / "WRITE_PROMPT.md"
    code, built = run(
        "build_write_prompt.py",
        ["--persona", str(persona), "--brief", str(dest_brief), "--out", str(wp)],
    )
    # AGENT_HANDOFF SSOT：skill 主控与 console 共用同一 spawn_prompt
    code_h, hand = run(
        "build_agent_handoff.py",
        [
            "--role",
            "writer",
            "--prompt",
            str(wp),
            "--out-dir",
            str(run_dir),
            "--write",
            str(run_dir / "draft.md"),
            "--persona",
            persona.name,
            "--run-id",
            run_id,
        ],
    )
    orch = hand.get("orchestrate") if isinstance(hand, dict) else {}
    return {
        "ok": code == 0 and code_h == 0,
        "stage": "prepare",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "write_prompt": str(wp),
        "draft_target": str(run_dir / "draft.md"),
        "agent_handoff": hand.get("handoff") if isinstance(hand, dict) else str(run_dir / "AGENT_HANDOFF.json"),
        "spawn_prompt": hand.get("spawn_prompt") if isinstance(hand, dict) else str(run_dir / "SPAWN_PROMPT.md"),
        "orchestrate": orch,
        "can_write": can,
        "next": "Spawn Writer with SPAWN_PROMPT.md → then --stage post",
        "spawn_instruction": (
            "读 SPAWN_PROMPT.md（或 AGENT_HANDOFF.json.spawn_prompt）整段注入 Writer 分身；"
            "分身只写 draft.md；主控/console 禁代写正文。"
        ),
    }


def stage_post(persona: Path, run_id: str, gates_only: bool) -> dict:
    run_dir = persona / "runs" / run_id
    draft = run_dir / "draft.md"
    brief = run_dir / "brief.md"
    if not draft.exists():
        return {"ok": False, "error": f"draft missing: {draft}", "hint": "Writer 未落盘"}

    gates = run_dir / "GATES.json"
    code_g, gates_data = run(
        "post_write_gates.py",
        [
            "--persona",
            str(persona),
            "--draft",
            str(draft),
            "--brief",
            str(brief),
            "--out",
            str(gates),
        ],
    )

    result: dict = {
        "ok": code_g == 0,
        "stage": "post",
        "run_id": run_id,
        "gates": str(gates),
        "gates_ok": gates_data.get("ok") if isinstance(gates_data, dict) else code_g == 0,
        "gates_data": gates_data if isinstance(gates_data, dict) else {},
    }

    if gates_only:
        # 合成 Judge：机检过即 pass（快路径）
        fake = {
            "pass": bool(result["gates_ok"]),
            "axis_a_fidelity": 0.75 if result["gates_ok"] else 0.4,
            "axis_b_brief": 0.85 if result["gates_ok"] else 0.3,
            "rules_compliance": 0.7,
            "identity_ok": (gates_data.get("identity") or {}).get("ok", True)
            if isinstance(gates_data, dict)
            else True,
            "caricature_risk": False,
            "manual_items": [],
            "fail_reasons": [] if result["gates_ok"] else ["gates_failed"],
            "rewrite_directives": []
            if result["gates_ok"]
            else ["按 GATES.json 失败项改 brief 合规与身份"],
            "one_line": "gates-only 快路径合成 Judge",
            "gates_only": True,
        }
        jp = run_dir / "JUDGE_SCORE.json"
        jp.write_text(json.dumps(fake, ensure_ascii=False, indent=2), encoding="utf-8")
        result["judge_score"] = str(jp)
        result["gates_only"] = True
        result["next"] = "run --stage finalize"
        return result

    jprompt = run_dir / "JUDGE_PROMPT.md"
    code_j, _ = run(
        "build_judge_prompt.py",
        [
            "--persona",
            str(persona),
            "--draft",
            str(draft),
            "--brief",
            str(brief),
            "--gates",
            str(gates),
            "--out",
            str(jprompt),
        ],
    )
    code_h, hand = run(
        "build_agent_handoff.py",
        [
            "--role",
            "judge",
            "--prompt",
            str(jprompt),
            "--out-dir",
            str(run_dir),
            "--write",
            str(run_dir / "JUDGE_SCORE.json"),
            "--persona",
            persona.name,
            "--run-id",
            run_id,
        ],
    )
    orch = hand.get("orchestrate") if isinstance(hand, dict) else {}
    result["judge_prompt"] = str(jprompt)
    result["agent_handoff"] = (
        hand.get("handoff") if isinstance(hand, dict) else str(run_dir / "AGENT_HANDOFF.json")
    )
    result["spawn_prompt"] = (
        hand.get("spawn_prompt") if isinstance(hand, dict) else str(run_dir / "SPAWN_PROMPT.md")
    )
    result["orchestrate"] = orch
    result["ok"] = result["ok"] and code_j == 0 and code_h == 0
    result["spawn_instruction"] = (
        "读 SPAWN_PROMPT.md 整段注入 Judge 分身；只写 JUDGE_SCORE.json；禁改 draft。"
    )
    # 机检失败仍生成 Judge prompt，但 next 可先回炉 Writer
    if not result["gates_ok"]:
        result["next"] = "gates failed → 回炉 Writer 或仍跑 Judge；finalize 将 deliver_ok=false"
    else:
        result["next"] = "Spawn Judge with SPAWN_PROMPT.md → then --stage finalize"
    return result


def stage_finalize(persona: Path, run_id: str, gates_only: bool, keep_runs: int) -> dict:
    run_dir = persona / "runs" / run_id
    draft = run_dir / "draft.md"
    brief = run_dir / "brief.md"
    gates = run_dir / "GATES.json"
    judge = run_dir / "JUDGE_SCORE.json"
    if not draft.exists():
        return {"ok": False, "error": "draft missing"}
    if not gates.exists():
        return {"ok": False, "error": "GATES missing; run --stage post first"}
    if not judge.exists():
        return {"ok": False, "error": "JUDGE_SCORE missing; run Judge or --gates-only post"}

    hard_path = persona / "runs" / "_last_draft_metrics.json"
    # score_loop already in post_write_gates; dual_axis accepts score_loop shape via --hard
    # rebuild thin hard from gates if needed
    deliver = run_dir / "DELIVER.json"
    hard_arg = []
    if hard_path.exists():
        # wrap as score_loop-like
        try:
            hm = json.loads(hard_path.read_text(encoding="utf-8"))
            score = hm.get("score_vs_anchor")
            thin = {"ok": True, "score_vs_anchor": score, "summary": hm}
            hp = run_dir / "HARD.json"
            hp.write_text(json.dumps(thin, ensure_ascii=False), encoding="utf-8")
            hard_arg = ["--hard", str(hp)]
        except json.JSONDecodeError:
            pass

    code_d, deliv = run(
        "dual_axis_gate.py",
        [
            "--judge",
            str(judge),
            "--gates",
            str(gates),
            *hard_arg,
            "--out",
            str(deliver),
        ],
    )

    code_r, receipt = run(
        "build_receipt.py",
        [
            "--persona",
            str(persona),
            "--draft",
            str(draft),
            "--brief",
            str(brief),
            "--gates",
            str(gates),
            "--deliver",
            str(deliver),
            "--judge",
            str(judge),
            "--out-dir",
            str(run_dir),
            *(["--gates-only"] if gates_only else []),
        ],
    )

    gates_ok = bool(isinstance(deliv, dict) and deliv.get("gates_ok", True))
    judge_pass = bool(isinstance(deliv, dict) and deliv.get("judge_pass"))
    hard_score = deliv.get("hard_score") if isinstance(deliv, dict) else None
    run(
        "loop_state.py",
        [
            "--persona",
            str(persona),
            "record",
            "--run-id",
            run_id,
            "--gates-ok",
            "true" if gates_ok else "false",
            "--judge-pass",
            "true" if judge_pass else "false",
            *(["--hard-score", str(hard_score)] if hard_score is not None else []),
        ],
    )

    deliver_ok = bool(isinstance(deliv, dict) and deliv.get("deliver_ok"))
    run(
        "loop_state.py",
        [
            "--persona",
            str(persona),
            "finalize",
            "--result",
            "passed" if deliver_ok else "exhausted",
        ],
    )

    run(
        "hygiene_persona.py",
        ["--persona", str(persona), "--keep-runs", str(keep_runs)],
    )

    return {
        "ok": deliver_ok,
        "stage": "finalize",
        "run_id": run_id,
        "deliver_ok": deliver_ok,
        "draft": str(draft),
        "receipt_json": str(run_dir / "RECEIPT.json"),
        "receipt_md": str(run_dir / "RECEIPT.md"),
        "deliver": deliv if isinstance(deliv, dict) else {},
        "receipt": receipt if isinstance(receipt, dict) else {},
        "dual_exit": code_d,
        "receipt_exit": code_r,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="magicpen Write facade")
    ap.add_argument("--persona", type=str, required=True, help="id 或路径")
    ap.add_argument("--brief", type=Path, required=True)
    ap.add_argument(
        "--stage",
        choices=["prepare", "post", "finalize", "auto"],
        default="prepare",
    )
    ap.add_argument("--run-id", type=str, default="")
    ap.add_argument("--max-loops", type=int, default=5)
    ap.add_argument("--gates-only", action="store_true", help="明文快路径：跳过 Judge 分身")
    ap.add_argument("--keep-runs", type=int, default=1)
    args = ap.parse_args()

    try:
        persona = resolve_persona(args.persona)
    except FileNotFoundError as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 2

    if not args.brief.exists():
        print(json.dumps({"ok": False, "error": f"brief missing: {args.brief}"}, ensure_ascii=False))
        return 2

    run_id = args.run_id or next_run_id(persona)

    if args.stage == "prepare":
        report = stage_prepare(persona, args.brief, run_id, args.max_loops)
    elif args.stage == "post":
        if not args.run_id:
            # latest run with draft or newest dir
            runs = sorted((persona / "runs").glob("r*"), key=lambda p: p.stat().st_mtime, reverse=True)
            if not runs:
                print(json.dumps({"ok": False, "error": "no runs; prepare first"}, ensure_ascii=False))
                return 2
            run_id = runs[0].name
        report = stage_post(persona, run_id, args.gates_only)
    elif args.stage == "finalize":
        if not args.run_id:
            runs = sorted((persona / "runs").glob("r*"), key=lambda p: p.stat().st_mtime, reverse=True)
            run_id = runs[0].name if runs else run_id
        report = stage_finalize(persona, run_id, args.gates_only, args.keep_runs)
    else:  # auto
        report = stage_prepare(persona, args.brief, run_id, args.max_loops)
        draft = Path(report.get("draft_target") or "")
        # if user pre-seeded draft into run (copy), continue
        if draft.exists() and draft.stat().st_size > 0:
            post = stage_post(persona, run_id, args.gates_only)
            report["post"] = post
            if (persona / "runs" / run_id / "JUDGE_SCORE.json").exists():
                fin = stage_finalize(persona, run_id, args.gates_only, args.keep_runs)
                report["finalize"] = fin
                report["ok"] = fin.get("ok")
                report["deliver_ok"] = fin.get("deliver_ok")
            else:
                report["next"] = post.get("next")
        else:
            report["next"] = "Writer must write draft then --stage post"

    report["persona"] = str(persona)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
