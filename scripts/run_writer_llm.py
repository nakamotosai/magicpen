#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""W3 一键：读 WRITE_PROMPT → cliproxy Grok 写 draft.md。

控制台默认路径；skill 主控也可调（不必再外置 Writer 分身）。
外置 SPAWN 仍保留在 run 目录供高级复制。

  pythonw run_writer_llm.py --run-dir personas/x/runs/rN
  pythonw run_writer_llm.py --write-prompt WP.md --draft draft.md
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


def han_count(t: str) -> int:
    return len(re.findall(r"[一-鿿]", t or ""))


def strip_fences(text: str) -> str:
    t = (text or "").strip()
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
    return t.strip()


def looks_meta(text: str) -> bool:
    if not text or han_count(text) < 80:
        return True
    head = text[:400]
    return bool(
        re.search(
            r"我将|正在写|写入路径|draft\.md|WRITE_PROMPT|如下所示|好的[，,]|"
            r"作为 Writer|按要求开始|下面是正文",
            head,
        )
    )


def build_runtime_prompt(write_prompt_body: str) -> str:
    body = (write_prompt_body or "").strip()
    return (
        "任务：按下方 WRITE_PROMPT 写**一篇完整新文正文**。\n\n"
        "## 你必须遵守\n"
        "1. **整条回复只能是正文**。禁止「好的」「如下」「我将写入」等任何元话。\n"
        "2. 学的是笔迹与节奏，不是样本身份/角色/物种壳；brief 没要求角色仿写就禁止搬壳。\n"
        "3. 禁止复述 brief、禁止输出评分、禁止 Markdown 代码围栏、禁止标题「正文：」。\n"
        "4. 字数/结构/禁词以 WRITE_PROMPT 里的 brief 为准。\n"
        "5. 不要提文件路径、工具、卡卡西、Grok。\n\n"
        "========== WRITE_PROMPT 全文开始 ==========\n\n"
        f"{body}\n\n"
        "========== WRITE_PROMPT 全文结束 ==========\n\n"
        "现在只输出新文正文：\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="kakashi writer via cliproxy LLM")
    ap.add_argument("--run-dir", type=Path, default=None)
    ap.add_argument("--write-prompt", type=Path, default=None)
    ap.add_argument("--draft", type=Path, default=None)
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--max-tokens", type=int, default=8192)
    args = ap.parse_args()

    run_dir = args.run_dir
    if run_dir:
        run_dir = run_dir.resolve()
        wp = args.write_prompt or (run_dir / "WRITE_PROMPT.md")
        draft = args.draft or (run_dir / "draft.md")
    else:
        wp = args.write_prompt
        draft = args.draft
        run_dir = (draft.parent if draft else Path("."))
    if not wp or not Path(wp).is_file():
        print(json.dumps({"ok": False, "error": "WRITE_PROMPT 不存在；先 run_write --stage prepare"}, ensure_ascii=False))
        return 2
    if not draft:
        print(json.dumps({"ok": False, "error": "需要 --draft 或 --run-dir"}, ensure_ascii=False))
        return 2
    draft = Path(draft)
    draft.parent.mkdir(parents=True, exist_ok=True)

    body = Path(wp).read_text(encoding="utf-8", errors="replace")
    if han_count(body) < 50:
        print(json.dumps({"ok": False, "error": "WRITE_PROMPT 过短/空"}, ensure_ascii=False))
        return 2

    runtime = run_dir / "SPAWN_PROMPT_RUNTIME_WRITER.md"
    runtime.write_text(build_runtime_prompt(body), encoding="utf-8")

    llm_args = [
        str(SCRIPTS / "cliproxy_chat.py"),
        "--prompt",
        str(runtime),
        "--out",
        str(draft),
        "--system",
        "你是文学写手。用户给你写作合同（WRITE_PROMPT）时，你的整条回复只能是新文正文本身。"
        "禁止解释、禁止承认指令、禁止说正在写入文件、禁止 Markdown 代码围栏。",
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

    text = draft.read_text(encoding="utf-8", errors="replace") if draft.is_file() else ""
    text = strip_fences(text)
    if looks_meta(text):
        retry = (
            "上一次输出不合格（像在说话或太短）。\n"
            "严格重做：从第一个字到最后一个字都是新文正文。\n"
            "再读一遍合同，只交正文。\n\n"
            + build_runtime_prompt(body)
        )
        runtime.write_text(retry, encoding="utf-8")
        code2, out2, err2 = run_py(llm_args)
        llm2 = parse_json(out2)
        if code2 == 0 and llm2.get("ok"):
            llm = llm2
            text = strip_fences(
                draft.read_text(encoding="utf-8", errors="replace") if draft.is_file() else ""
            )

    text = strip_fences(text)
    draft.write_text(text.strip() + ("\n" if text.strip() else ""), encoding="utf-8")
    han = han_count(text)

    # 正文快照进 meta：防止会话重置/空写把 draft.md 清掉后无法恢复
    snap = text.strip()
    report = {
        "ok": han >= 80,
        "stage": "done",
        "draft": str(draft.resolve()),
        "write_prompt": str(Path(wp).resolve()),
        "runtime_prompt": str(runtime.resolve()),
        "han": han,
        "model": llm.get("model"),
        "llm_base": llm.get("base"),
        "usage": llm.get("usage"),
        "meta_retry": looks_meta(text) is False or han >= 80,
        "error": None if han >= 80 else f"正文过短或像元话（han={han}）",
        "text": snap[:20000],
        "text_truncated": len(snap) > 20000,
    }
    (run_dir / "WRITER_LLM.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
