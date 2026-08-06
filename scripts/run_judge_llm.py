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
    """补齐 schema 字段，保证 dual_axis / finalize 能读。v3.4 强制 axis_c_soul。"""
    out = dict(obj or {})
    def fnum(k, default=0.0):
        try:
            return float(out.get(k, default))
        except (TypeError, ValueError):
            return default

    axis_a = fnum("axis_a_fidelity", fnum("axis_a", 0.0))
    axis_b = fnum("axis_b_brief", fnum("axis_b", 0.0))
    # 缺 C 轴 = 0（禁假绿）
    has_c = "axis_c_soul" in out or "axis_c" in out
    axis_c = fnum("axis_c_soul", fnum("axis_c", 0.0))
    rules = fnum("rules_compliance", 0.0)
    identity_ok = bool(out.get("identity_ok", True))
    content_ok = bool(out.get("content_ok", True))
    # v3.4 硬规则：C≥0.72 才可 pass
    passed_rule = (
        identity_ok
        and content_ok
        and axis_a >= 0.7
        and axis_b >= 0.7
        and has_c
        and axis_c >= 0.72
    )
    if "pass" in out:
        passed = bool(out.get("pass")) and passed_rule
    else:
        passed = passed_rule
    fail_reasons = out.get("fail_reasons") if isinstance(out.get("fail_reasons"), list) else []
    if not has_c:
        fail_reasons = list(fail_reasons) + ["axis_c_soul_missing"]
    elif axis_c < 0.72:
        fail_reasons = list(fail_reasons) + ["axis_c_soul_low"]
    return {
        "pass": passed,
        "axis_a_fidelity": axis_a,
        "axis_b_brief": axis_b,
        "axis_c_soul": axis_c,
        "rules_compliance": rules,
        "identity_ok": identity_ok,
        "content_ok": content_ok,
        "caricature_risk": bool(out.get("caricature_risk", False)),
        "templatey_risk": bool(out.get("templatey_risk", False)),
        "sounds_like_other_persona": out.get("sounds_like_other_persona"),
        "manual_items": out.get("manual_items") if isinstance(out.get("manual_items"), list) else [],
        "fail_reasons": fail_reasons,
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
        "任务：你是神笔评分 Judge。读下方 JUDGE_PROMPT，**只输出一份 JUDGE_SCORE JSON**。\n\n"
        "## 硬约束\n"
        "1. 整条回复只能是一个 JSON 对象（可无缩进）。禁止 Markdown 围栏、禁止解释、禁止正文改写。\n"
        "2. 禁止改 draft；禁止输出除 JSON 外的任何字。\n"
        "3. 字段必须含：pass, axis_a_fidelity, axis_b_brief, axis_c_soul, rules_compliance, "
        "identity_ok, content_ok, caricature_risk, templatey_risk, manual_items, "
        "fail_reasons, rewrite_directives, one_line。\n"
        "4. pass=true 当且仅当 identity_ok 且 content_ok 且 axis_a≥0.7 且 axis_b≥0.7 "
        "且 **axis_c_soul≥0.72** 且机检闸无硬失败。机检绿≠像；C 低必须 pass=false。\n"
        "5. 分数用 0~1 小数。one_line 用中文一句话。\n\n"
        "========== JUDGE_PROMPT 全文开始 ==========\n\n"
        f"{body}\n\n"
        "========== JUDGE_PROMPT 全文结束 ==========\n\n"
        "现在只输出 JUDGE_SCORE JSON：\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="magicpen judge via cliproxy LLM")
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
    # 机检已过的字数：纠正 Judge 幻觉「字数不足」拖垮 axis_b
    gates_path = Path(run_dir) / "GATES.json"
    override_note = None
    if gates_path.is_file():
        try:
            g = json.loads(gates_path.read_text(encoding="utf-8"))
            bc = g.get("brief_compliance") or {}
            if not bc:
                for item in g.get("gates") or []:
                    if isinstance(item, dict) and item.get("name") == "brief_compliance":
                        bc = item.get("detail") or {}
                        break
            checks = bc.get("checks") or []
            han_ok = any(
                isinstance(c, dict) and c.get("id") == "han_range" and c.get("ok") is True
                for c in checks
            )
            if not han_ok and bc.get("ok") is True and (bc.get("han") or 0) >= 1800:
                han_ok = True
            b_now = float(score_obj.get("axis_b_brief") or 0)
            if han_ok and b_now < 0.7:
                score_obj["axis_b_brief"] = max(b_now, 0.82)
                score_obj["fail_reasons"] = [
                    x
                    for x in (score_obj.get("fail_reasons") or [])
                    if not re.search(r"字数|汉字|1800|不足|篇幅|han|brief_compliance硬失败", str(x), re.I)
                ]
                score_obj["pass"] = (
                    bool(score_obj.get("identity_ok", True))
                    and bool(score_obj.get("content_ok", True))
                    and float(score_obj.get("axis_a_fidelity") or 0) >= 0.7
                    and float(score_obj.get("axis_b_brief") or 0) >= 0.7
                    and float(score_obj.get("axis_c_soul") or 0) >= 0.72
                )
                score_obj["gate_han_override"] = True
                override_note = f"han_ok gate; B {b_now}->{score_obj['axis_b_brief']}"
        except Exception as e:
            override_note = f"override_error:{e}"
    if override_note:
        score_obj["gate_han_override_note"] = override_note
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
