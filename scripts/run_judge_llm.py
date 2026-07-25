#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W5 一键：读 JUDGE_PROMPT / SPAWN → cliproxy Grok 写 JUDGE_SCORE.json。

控制台默认路径；与 run_writer_llm 同栈。高级仍可手贴 JSON。

  pythonw run_judge_llm.py --run-dir personas/x/runs/rN
  pythonw run_judge_llm.py --judge-prompt JP.md --score JUDGE_SCORE.json
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def run_py(args: list[str]) -> tuple[int, str, str]:
    p = subprocess.run(
        [sys.executable, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=CREATE_NO_WINDOW,
    )
    return p.returncode, p.stdout or "", p.stderr or ""


def parse_json(stdout: str) -> dict:
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        i, j = stdout.find("{"), stdout.rfind("}") + 1
        if i >= 0 and j > i:
            try:
                return json.loads(stdout[i:j])
            except json.JSONDecodeError:
                pass
    return {}


def strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


def extract_json_obj(text: str) -> dict | None:
    t = strip_fences(text or "")
    if not t:
        return None
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    i, j = t.find("{"), t.rfind("}") + 1
    if i >= 0 and j > i:
        try:
            obj = json.loads(t[i:j])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def normalize_score(obj: dict) -> dict:
    """补齐 schema 字段，保证 dual_axis / finalize 能读。"""
    out = dict(obj or {})
    def fnum(k, default=0.0):
        try:
            return float(out.get(k, default))
        except (TypeError, ValueError):
            return default

    axis_a = fnum("axis_a_fidelity", fnum("axis_a", 0.0))
    axis_b = fnum("axis_b_brief", fnum("axis_b", 0.0))
    rules = fnum("rules_compliance", 0.0)
    identity_ok = bool(out.get("identity_ok", True))
    # 若模型给了 pass，尊重；否则按规则推
    if "pass" in out:
        passed = bool(out.get("pass"))
    else:
        passed = identity_ok and axis_a >= 0.7 and axis_b >= 0.7
    return {
        "pass": passed,
        "axis_a_fidelity": axis_a,
        "axis_b_brief": axis_b,
        "rules_compliance": rules,
        "identity_ok": identity_ok,
        "caricature_risk": bool(out.get("caricature_risk", False)),
        "manual_items": out.get("manual_items") if isinstance(out.get("manual_items"), list) else [],
        "fail_reasons": out.get("fail_reasons") if isinstance(out.get("fail_reasons"), list) else [],
        "rewrite_directives": out.get("rewrite_directives")
        if isinstance(out.get("rewrite_directives"), list)
        else [],
        "one_line": str(out.get("one_line") or out.get("summary") or "")[:240],
        "gates_only": False,
        "source": "judge_llm",
    }


def build_runtime_prompt(judge_body: str) -> str:
    body = (judge_body or "").strip()
    return (
        "任务：你是卡卡西评分 Judge。读下方 JUDGE_PROMPT，**只输出一份 JUDGE_SCORE JSON**。\n\n"
        "## 硬约束\n"
        "1. 整条回复只能是一个 JSON 对象（可无缩进）。禁止 Markdown 围栏、禁止解释、禁止正文改写。\n"
        "2. 禁止改 draft；禁止输出除 JSON 外的任何字。\n"
        "3. 字段必须含：pass, axis_a_fidelity, axis_b_brief, rules_compliance, identity_ok, "
        "caricature_risk, manual_items, fail_reasons, rewrite_directives, one_line。\n"
        "4. pass=true 当且仅当 identity_ok 且 axis_a_fidelity≥0.7 且 axis_b_brief≥0.7 "
        "且机检闸无硬失败（见 JUDGE_PROMPT 第5节 ok）。\n"
        "5. 分数用 0~1 小数。one_line 用中文一句话。\n\n"
        "========== JUDGE_PROMPT 全文开始 ==========\n\n"
        f"{body}\n\n"
        "========== JUDGE_PROMPT 全文结束 ==========\n\n"
        "现在只输出 JUDGE_SCORE JSON：\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="kakashi judge via cliproxy LLM")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--judge-prompt", type=Path, default=None)
    ap.add_argument("--score", type=Path, default=None, help="JUDGE_SCORE.json 路径")
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--max-tokens", type=int, default=4096)
    args = ap.parse_args()

    run_dir = args.run_dir
    if run_dir:
        run_dir = run_dir.resolve()
        jp = args.judge_prompt or (run_dir / "JUDGE_PROMPT.md")
        # 没有 JUDGE_PROMPT 时退 SPAWN（内含完整合同）
        if not jp.is_file():
            jp = run_dir / "SPAWN_PROMPT.md"
        score = args.score or (run_dir / "JUDGE_SCORE.json")
    else:
        jp = args.judge_prompt
        score = args.score
        run_dir = (score.parent if score else Path("."))
    if not jp or not Path(jp).is_file():
        print(
            json.dumps(
                {"ok": False, "error": "JUDGE_PROMPT/SPAWN 不存在；先跑 W4 机器硬闸"},
                ensure_ascii=False,
            )
        )
        return 2
    if not score:
        print(json.dumps({"ok": False, "error": "需要 --score 或 --run-dir"}, ensure_ascii=False))
        return 2
    score = Path(score)
    score.parent.mkdir(parents=True, exist_ok=True)

    body = Path(jp).read_text(encoding="utf-8", errors="replace")
    if len(body.strip()) < 80:
        print(json.dumps({"ok": False, "error": "评分合同过短/空"}, ensure_ascii=False))
        return 2

    runtime = run_dir / "SPAWN_PROMPT_RUNTIME_JUDGE.md"
    runtime.write_text(build_runtime_prompt(body), encoding="utf-8")
    raw_out = run_dir / "JUDGE_LLM_RAW.txt"

    llm_args = [
        str(SCRIPTS / "cliproxy_chat.py"),
        "--prompt",
        str(runtime),
        "--out",
        str(raw_out),
        "--system",
        "你是文学评分器。用户给你 JUDGE_PROMPT 时，你的整条回复只能是一个 JSON 对象 "
        "（JUDGE_SCORE）。禁止解释、禁止 Markdown 围栏、禁止输出正文。",
        "--max-tokens",
        str(args.max_tokens),
    ]
    if args.model:
        llm_args.extend(["--model", args.model])

    code, out, err = run_py(llm_args)
    llm = parse_json(out)
    if code != 0 or not llm.get("ok"):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": llm.get("error") or err or "llm failed",
                    "stage": "llm",
                },
                ensure_ascii=False,
            )
        )
        return 1

    raw_text = raw_out.read_text(encoding="utf-8", errors="replace") if raw_out.is_file() else ""
    obj = extract_json_obj(raw_text)
    meta_retry = False
    if not obj:
        meta_retry = True
        retry = (
            "上一次输出不是合法 JSON。\n"
            "严格重做：从第一个字符 { 到最后一个 } 必须是完整 JUDGE_SCORE。\n"
            "禁止任何前缀后缀。\n\n"
            + build_runtime_prompt(body)
        )
        runtime.write_text(retry, encoding="utf-8")
        code2, out2, err2 = run_py(llm_args)
        llm2 = parse_json(out2)
        if code2 == 0 and llm2.get("ok"):
            llm = llm2
            raw_text = raw_out.read_text(encoding="utf-8", errors="replace") if raw_out.is_file() else ""
            obj = extract_json_obj(raw_text)

    if not obj:
        report = {
            "ok": False,
            "stage": "parse",
            "error": "模型未产出合法 JUDGE_SCORE JSON",
            "raw_preview": (raw_text or "")[:400],
            "model": llm.get("model"),
        }
        (run_dir / "JUDGE_LLM.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1

    score_obj = normalize_score(obj)
    score.write_text(json.dumps(score_obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report = {
        "ok": True,
        "stage": "done",
        "score": str(score.resolve()),
        "judge_prompt": str(Path(jp).resolve()),
        "runtime_prompt": str(runtime.resolve()),
        "pass": score_obj.get("pass"),
        "axis_a_fidelity": score_obj.get("axis_a_fidelity"),
        "axis_b_brief": score_obj.get("axis_b_brief"),
        "one_line": score_obj.get("one_line"),
        "model": llm.get("model"),
        "llm_base": llm.get("base"),
        "usage": llm.get("usage"),
        "meta_retry": meta_retry,
        "score_obj": score_obj,
        "error": None,
    }
    (run_dir / "JUDGE_LLM.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
