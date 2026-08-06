#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""AGENT_HANDOFF SSOT：Writer / Judge / Sample-Search 分身注入包。

skill 主控与 console「跑本步」必须用同一份 spawn_prompt。
Python 不代替分身写正文；本脚本只组装交接物。

  pythonw build_agent_handoff.py --role writer --prompt WRITE_PROMPT.md --out-dir RUN/
  pythonw build_agent_handoff.py --role judge  --prompt JUDGE_PROMPT.md --out-dir RUN/
  pythonw build_agent_handoff.py --role sample_search --query-file q.md --out-dir SESSION/
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def sample_search_package(
    query: str,
    raw_path: Path,
    *,
    session_id: str = "",
    min_han: int = 500,
    max_han: int = 3000,
) -> dict:
    """网搜范文分身：按用户要求找公开作品，清洗后写入 raw.md。"""
    q = (query or "").strip()
    spawn = (
        "你是【神笔 范文搜集分身】。任务：按用户要求，从公开网络找可学**笔迹**的范文，"
        "清洗后写入指定 raw 路径。\n\n"
        "## 硬约束\n"
        "1. **只搜集公开可引用文本**；不碰付费墙破解、盗版站、隐私泄露。\n"
        "2. 目标是**文风样本**，不是百科简介、不是评论区、不是营销软文目录。\n"
        "3. 清洗：去导航/页脚/广告/分享按钮/「相关阅读」；保留作者正文段落与必要标点换行。\n"
        "4. 汉字量目标：**≥"
        f"{min_han}**，尽量 ≤**{max_han}**（超了就截到完整段落边界，勿半句砍断）。\n"
        "5. **禁止代写、禁止用自己的文风补全**；搜不到就写清楚缺什么，不要瞎编范文。\n"
        "6. **风格 ≠ 身份提醒**：你交的是 sample 原文；下游会学笔迹，不学角色壳。"
        "若用户点名某虚构角色口吻，仍只交该作者公开文本，不要写成角色扮演稿。\n"
        "7. 工具：优先 search / fetch / social 只读；写文件只允许 raw 路径。\n\n"
        f"## 路径\n"
        f"- 会话：{session_id or '(console session)'}\n"
        f"- **raw 落盘路径（必须写这里）**：{raw_path.resolve()}\n\n"
        "## 用户搜范文要求\n"
        f"{q}\n\n"
        "## 交付格式\n"
        "1. 用 Write/Edit 把**清洗后的纯正文**写入 raw 路径（Markdown 纯文本即可，无需要求 YAML）。\n"
        "2. 若只能回消息：回复**仅含正文**（无前言后语），由编排器落盘。\n"
        "3. 正文开头可用一行 HTML 注释记下来源（可选）：\n"
        "   <!-- source: URL 或书名篇名 -->\n"
        "4. 不要输出评分、不要输出「我搜了哪些站」长文（来源一行足够）。\n\n"
        "现在开始搜集并写入 raw。\n"
    )
    return {
        "role": "sample_search",
        "next_agent": "sample_search",
        "session_id": session_id,
        "query": q,
        "read": None,
        "write": str(raw_path.resolve()),
        "rules": [
            "只搜公开文本",
            "只写 raw.md",
            "清洗网页壳",
            f"汉字 {min_han}–{max_han}",
            "禁代写禁补造",
            "风格样本≠角色扮演稿",
        ],
        "spawn_prompt": spawn,
        "version": "3.3.2",
    }


def writer_package(
    write_prompt: Path,
    draft_path: Path,
    *,
    persona: str = "",
    run_id: str = "",
) -> dict:
    body = write_prompt.read_text(encoding="utf-8")
    spawn = (
        "你是【神笔 Writer 分身】。本任务只做一件事：按 WRITE_PROMPT 写 draft。\n\n"
        "## 硬约束\n"
        "1. **只吃**下面 WRITE_PROMPT 全文（已含 sample 笔迹 + rules + brief）。\n"
        "2. **只写**输出路径中的 draft 正文；禁止改 persona 包其它文件。\n"
        "3. **风格 ≠ 身份**：学句式/节奏/换行，不学样本叙事者物种/角色/世界壳，"
        "除非 brief 明文允许角色仿写。\n"
        "4. 禁止摘要 brief、禁止续写样本故事、禁止输出评分或解释。\n"
        "5. 写完自检 brief 硬条件（字数/结构/禁词）。\n\n"
        f"## 路径\n"
        f"- 人格：{persona or '(见 prompt)'}\n"
        f"- run：{run_id or '(见路径)'}\n"
        f"- WRITE_PROMPT 源文件：{write_prompt.resolve()}\n"
        f"- **draft 落盘路径（必须写这里）**：{draft_path.resolve()}\n\n"
        "## 工具环境\n"
        "若有 Write/Edit 工具：把**完整正文**写入 draft 路径（覆盖）。\n"
        "若只能回消息：回复**仅含正文**（无 Markdown 围栏、无前言后语），"
        "由编排器落盘。\n\n"
        "========== WRITE_PROMPT 全文开始 ==========\n\n"
        f"{body}\n\n"
        "========== WRITE_PROMPT 全文结束 ==========\n\n"
        "现在开始写 draft。只交正文。\n"
    )
    return {
        "role": "writer",
        "next_agent": "writer",
        "persona": persona,
        "run_id": run_id,
        "read": str(write_prompt.resolve()),
        "write": str(draft_path.resolve()),
        "rules": [
            "只吃 WRITE_PROMPT",
            "只写 draft.md",
            "风格≠身份",
            "写完自检 brief 硬条件",
            "禁改 persona 其它文件",
        ],
        "spawn_prompt": spawn,
        "version": "3.3.1",
    }


def judge_package(
    judge_prompt: Path,
    score_path: Path,
    *,
    persona: str = "",
    run_id: str = "",
) -> dict:
    body = judge_prompt.read_text(encoding="utf-8")
    spawn = (
        "你是【神笔 Judge 分身】。本任务只做一件事：读 JUDGE_PROMPT，输出评分 JSON。\n\n"
        "## 硬约束\n"
        "1. **只吃**下面 JUDGE_PROMPT 全文。\n"
        "2. **只写** JUDGE_SCORE.json（唯一 JSON 对象，无 Markdown 围栏）。\n"
        "3. 双轴：A=笔迹 fidelity；B=brief 合规。硬分旁证不得单独 PASS。\n"
        "4. 身份污染 → identity_ok=false 且 pass=false。\n"
        "5. 禁止改 draft / persona / 其它文件；禁止代写正文。\n\n"
        f"## 路径\n"
        f"- 人格：{persona or '(见 prompt)'}\n"
        f"- run：{run_id or '(见路径)'}\n"
        f"- JUDGE_PROMPT 源文件：{judge_prompt.resolve()}\n"
        f"- **JUDGE_SCORE 落盘路径**：{score_path.resolve()}\n\n"
        "## 工具环境\n"
        "若有 Write 工具：把 JSON 写入 score 路径。\n"
        "若只能回消息：回复**仅一个 JSON 对象**。\n\n"
        "========== JUDGE_PROMPT 全文开始 ==========\n\n"
        f"{body}\n\n"
        "========== JUDGE_PROMPT 全文结束 ==========\n\n"
        "现在输出 JUDGE_SCORE.json。\n"
    )
    return {
        "role": "judge",
        "next_agent": "judge",
        "persona": persona,
        "run_id": run_id,
        "read": str(judge_prompt.resolve()),
        "write": str(score_path.resolve()),
        "rules": [
            "只输出 JSON",
            "双轴 A/B",
            "身份失败则 pass=false",
            "禁改 draft/persona",
        ],
        "spawn_prompt": spawn,
        "version": "3.3.1",
    }


def write_handoff(pkg: dict, out_dir: Path, *, spawn_name: str = "SPAWN_PROMPT.md") -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    handoff = out_dir / "AGENT_HANDOFF.json"
    spawn_p = out_dir / spawn_name
    orch = {
        "next_agent": pkg["next_agent"],
        "read": pkg.get("read"),
        "write": pkg["write"],
        "rules": pkg["rules"],
        "handoff": str(handoff.resolve()),
        "spawn_prompt_file": str(spawn_p.resolve()),
        "version": pkg.get("version"),
    }
    handoff.write_text(json.dumps(pkg, ensure_ascii=False, indent=2), encoding="utf-8")
    spawn_p.write_text(pkg["spawn_prompt"], encoding="utf-8")
    (out_dir / "ORCHESTRATE.json").write_text(
        json.dumps(orch, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return {
        "ok": True,
        "role": pkg["role"],
        "handoff": str(handoff.resolve()),
        "spawn_prompt": str(spawn_p.resolve()),
        "orchestrate": orch,
        "read": pkg.get("read"),
        "write": pkg["write"],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="magicpen AGENT_HANDOFF SSOT")
    ap.add_argument(
        "--role",
        choices=["writer", "judge", "sample_search"],
        required=True,
    )
    ap.add_argument("--prompt", type=Path, default=None, help="WRITE_PROMPT 或 JUDGE_PROMPT")
    ap.add_argument("--out-dir", type=Path, required=True, help="run 或 console session 目录")
    ap.add_argument("--write", type=Path, default=None, help="draft / JUDGE_SCORE / raw 路径")
    ap.add_argument("--persona", type=str, default="")
    ap.add_argument("--run-id", type=str, default="")
    ap.add_argument("--query", type=str, default="", help="sample_search 用户要求（与 --query-file 二选一）")
    ap.add_argument("--query-file", type=Path, default=None, help="sample_search 要求文件")
    ap.add_argument("--session-id", type=str, default="")
    args = ap.parse_args()

    out_dir = args.out_dir
    if args.role == "sample_search":
        if args.query_file and args.query_file.is_file():
            q = args.query_file.read_text(encoding="utf-8")
        else:
            q = args.query
        if not (q or "").strip():
            print(json.dumps({"ok": False, "error": "sample_search 需要 --query 或 --query-file"}, ensure_ascii=False))
            return 2
        raw = args.write or (out_dir / "raw.md")
        pkg = sample_search_package(
            q, raw, session_id=args.session_id or args.run_id or out_dir.name
        )
        # 避免覆盖写稿 SPAWN：范文搜集用专用文件名，同时仍写 SPAWN_PROMPT.md 给 console 统一复制
        report = write_handoff(pkg, out_dir, spawn_name="SPAWN_PROMPT.md")
        (out_dir / "SAMPLE_SEARCH_QUERY.md").write_text(q.strip() + "\n", encoding="utf-8")
        report["query_file"] = str((out_dir / "SAMPLE_SEARCH_QUERY.md").resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    if not args.prompt or not args.prompt.is_file():
        print(json.dumps({"ok": False, "error": f"prompt missing: {args.prompt}"}, ensure_ascii=False))
        return 2

    if args.role == "writer":
        draft = args.write or (out_dir / "draft.md")
        pkg = writer_package(
            args.prompt, draft, persona=args.persona, run_id=args.run_id or out_dir.name
        )
    else:
        score = args.write or (out_dir / "JUDGE_SCORE.json")
        pkg = judge_package(
            args.prompt, score, persona=args.persona, run_id=args.run_id or out_dir.name
        )

    report = write_handoff(pkg, out_dir)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
