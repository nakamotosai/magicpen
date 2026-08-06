#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""I1 一键：组装 sample_search SPAWN → cliproxy Grok 写 raw → 清洗。

控制台/主控都可调；密钥只经环境变量（见 cliproxy_chat.py）。

  pythonw run_sample_search_llm.py --query-file q.md --out-dir SESSION/ --write SESSION/raw.md
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
    cmd = [sys.executable, *args]
    p = subprocess.run(
        cmd,
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


def han_count(t: str) -> int:
    return len(re.findall(r"[一-鿿]", t or ""))


def main() -> int:
    ap = argparse.ArgumentParser(description="magicpen sample_search via cliproxy LLM")
    ap.add_argument("--query", type=str, default="")
    ap.add_argument("--query-file", type=Path, default=None)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--write", type=Path, default=None, help="raw.md 路径")
    ap.add_argument("--session-id", type=str, default="")
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--skip-clean", action="store_true")
    args = ap.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = args.write or (out_dir / "raw.md")

    if args.query_file and args.query_file.is_file():
        q = args.query_file.read_text(encoding="utf-8")
    else:
        q = args.query
    if not (q or "").strip():
        print(json.dumps({"ok": False, "error": "需要 --query 或 --query-file"}, ensure_ascii=False))
        return 2

    qfile = out_dir / "SAMPLE_SEARCH_QUERY.md"
    qfile.write_text(q.strip() + "\n", encoding="utf-8")

    # 1) handoff SPAWN
    code, out, err = run_py(
        [
            str(SCRIPTS / "build_agent_handoff.py"),
            "--role",
            "sample_search",
            "--query-file",
            str(qfile),
            "--out-dir",
            str(out_dir),
            "--write",
            str(raw),
            "--session-id",
            args.session_id or out_dir.name,
        ]
    )
    ho = parse_json(out)
    if code != 0 and not ho.get("ok"):
        print(json.dumps({"ok": False, "error": ho.get("error") or err or "handoff failed", "stage": "handoff"}, ensure_ascii=False))
        return 1
    spawn = Path(ho.get("spawn_prompt") or (out_dir / "SPAWN_PROMPT.md"))
    if not spawn.is_file():
        print(json.dumps({"ok": False, "error": "SPAWN_PROMPT missing", "stage": "handoff"}, ensure_ascii=False))
        return 1

    # 2) LLM — 一键模式不用「Write 工具」口吻的 SPAWN 全文（否则模型只会回「正在写入路径」）
    # 仍保留 SPAWN 文件供高级复制；实际喂给 Grok 的是纯正文合同。
    llm_prompt = (
        "任务：输出可作「文风样本」的公开作品正文。\n\n"
        "## 用户要的范文\n"
        f"{q.strip()}\n\n"
        "## 你必须遵守\n"
        "1. **直接输出正文**。禁止说「我将写入」「如下所示」「好的」等任何元话。\n"
        "2. 无浏览器：用你对**公版/广为人知公开文本**的知识还原正文；不要编私人信件或假 URL。\n"
        "3. 文首可有且仅可有一行：`<!-- source: 作品名；memory-approx -->`\n"
        "4. 汉字尽量 **500–2000**；宁可完整段落，不要半句。\n"
        "5. 不要 Markdown 标题装饰、不要书评、不要作者简介长文。\n"
        "6. 不要提 raw 路径、不要提工具、不要提神笔。\n\n"
        "现在只输出正文：\n"
    )
    spawn_run = out_dir / "SPAWN_PROMPT_RUNTIME.md"
    spawn_run.write_text(llm_prompt, encoding="utf-8")

    llm_args = [
        str(SCRIPTS / "cliproxy_chat.py"),
        "--prompt",
        str(spawn_run),
        "--out",
        str(raw),
        "--system",
        "你是文学文本复述器。用户要范文正文时，你的整条回复只能是正文本身（可加一行 source 注释）。禁止任何解释、禁止承认指令、禁止说正在写入文件。",
        "--max-tokens",
        "4096",
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

    # 若仍是元话/过短，严格重试一次
    text0 = raw.read_text(encoding="utf-8", errors="replace") if raw.is_file() else ""
    meta_hit = bool(
        re.search(
            r"写入|路径|raw\.md|正在将|我来|如下|好的[，,]",
            text0,
        )
    )
    if han_count(text0) < 120 or meta_hit:
        retry_prompt = (
            "上一次输出不合格（像在说话而不是给正文）。\n"
            "严格重做：从第一个字到最后一个字都是作品正文。\n"
            f"作品要求：{q.strip()}\n"
            "只输出正文。\n"
        )
        spawn_run.write_text(retry_prompt, encoding="utf-8")
        code2, out2, err2 = run_py(llm_args)
        llm2 = parse_json(out2)
        if code2 == 0 and llm2.get("ok"):
            llm = llm2
            text0 = raw.read_text(encoding="utf-8", errors="replace") if raw.is_file() else text0

    # 3) clean
    notes = []
    if not args.skip_clean and raw.is_file():
        code, out, err = run_py(
            [
                str(SCRIPTS / "clean_sample_text.py"),
                "--in",
                str(raw),
                "--out",
                str(raw),
                "--include-text",
            ]
        )
        cl = parse_json(out)
        if cl.get("ok"):
            notes = cl.get("notes") or []
            han = cl.get("han_after")
        else:
            notes.append("清洗跳过: " + str(cl.get("error") or err))
            han = han_count(raw.read_text(encoding="utf-8", errors="replace"))
    else:
        han = han_count(raw.read_text(encoding="utf-8", errors="replace")) if raw.is_file() else 0

    report = {
        "ok": True,
        "stage": "done",
        "raw": str(raw.resolve()),
        "spawn_prompt": str(spawn.resolve()),
        "han": han,
        "model": llm.get("model"),
        "llm_base": llm.get("base"),
        "usage": llm.get("usage"),
        "notes": notes,
        "query_file": str(qfile.resolve()),
    }
    (out_dir / "SAMPLE_SEARCH_LLM.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
