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


def strip_em_dashes(text: str) -> str:
    """老蔡 brief 常 max_dash≈0；写后硬清 em/en dash，避免机检假挂。"""
    t = text or ""
    t = t.replace("——", "，")
    t = t.replace("—", "，")
    t = t.replace("–", "，")
    t = t.replace("―", "，")
    # 英文双连字符作破折时
    t = re.sub(r"(?<!\d)--(?!\d)", "，", t)
    return t


def normalize_h2(text: str) -> str:
    return re.sub(
        r"(?m)^(?!#)([一二三四五六七八九十]+、[^\n]{2,40})\s*$",
        r"## \1",
        text or "",
    )


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
        "2. 学的是笔迹与节奏 + mind 思维链，不是样本身份/角色壳；禁止复读 sample 事件。\n"
        "3. 禁止复述 brief、禁止输出评分、禁止 Markdown 代码围栏、禁止标题「正文：」。\n"
        "4. 字数/结构/禁词以 WRITE_PROMPT 里的 brief 为准；**写满字数下限**，勿交半成品提纲。\n"
        "5. 若 brief 要 `## 一、`… 编号节：正文**必须**用 `## 一、` 格式，禁止只写裸 `一、`。\n"
        "6. 按 mind：刺激→查证/场面→反差→判断→短收；**开篇禁止先抛总判金句**。\n"
        "7. 分节文：**每一节内部**须有场面或查证动作（翻/查/群里/答弁/现场），禁止纯履历点+金句。\n"
        "8. 禁止 brief 提纲朗读体；禁止节末同构金句；禁止船/漆/镜/车道隐喻刷屏。\n"
        "9. **禁止破折号**（— —— – ― --）；逗号/句号/空行断句。\n"
        "10. 像微信跟熟人解释：口语短锤+空行；禁文青隐喻串、禁特稿精修腔、禁政论金句排比。\n"
        "11. 不要提文件路径、工具、神笔、Grok。\n\n"
        "========== WRITE_PROMPT 全文开始 ==========\n\n"
        f"{body}\n\n"
        "========== WRITE_PROMPT 全文结束 ==========\n\n"
        "现在只输出新文正文：\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="magicpen writer via cliproxy LLM")
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

    text = strip_em_dashes(normalize_h2(strip_fences(text)))
    # brief 字数下限：不足则自动扩写一轮（v3.4 防短稿假绿）
    brief_min = None
    m_range = re.search(r"(\d{3,4})\s*[-–—~～至到]\s*(\d{3,4})\s*汉?字?", body)
    if m_range:
        brief_min = int(m_range.group(1))
    else:
        m_approx = re.search(r"约\s*(\d{3,4})\s*汉?字", body)
        if m_approx:
            brief_min = int(int(m_approx.group(1)) * 0.9)
    expanded = False
    expand_rounds = 0
    mind_rewrite = False
    dash_stripped = False
    han = han_count(text)

    def section_scene_ok(t: str) -> bool:
        tmp = run_dir / "_section_scene_tmp.md"
        tmp.write_text(t, encoding="utf-8")
        code_s, out_s, _ = run_py(
            [str(SCRIPTS / "assert_section_scene.py"), "--draft", str(tmp)]
        )
        try:
            return bool(json.loads(out_s).get("ok"))
        except Exception:
            return code_s == 0

    # v3.5：字数不足或中段提纲 → 先 mind 定向回炉 1 次，再轻量加厚
    need_mind = (brief_min and han < brief_min and han >= 80) or (
        han >= 80 and not section_scene_ok(text)
    )
    if need_mind:
        mind_prompt = (
            f"下面这篇被判定不合格（当前约 {han} 汉字"
            + (f"，目标至少 {brief_min}" if brief_min else "")
            + "；或中段像履历提纲）。\n"
            "请**整篇按 mind 回炉重写**（不是注水）：\n"
            "1) 开篇刺激→自己查证→冷热差→再判断；\n"
            "2) 每一节内部必须有场面/查证动作，禁止纯履历点+金句；\n"
            "3) 空行口语短锤（好家伙/满脸问号/咯）；像微信熟人，禁特稿/政论；\n"
            "4) **全篇禁止破折号**；禁样本事件、禁船漆镜/文青隐喻刷屏；\n"
            "5) 标题 `## 一、`… 可自拟；写满字数下限；只输出完整正文。\n\n"
            "===== 原文 =====\n"
            f"{text.strip()}\n"
            "===== 合同摘要 =====\n"
            f"{body[-3000:]}\n"
        )
        mp = run_dir / "_mind_rewrite_prompt.md"
        mp.write_text(mind_prompt, encoding="utf-8")
        m_args = [
            str(SCRIPTS / "cliproxy_chat.py"),
            "--prompt",
            str(mp),
            "--out",
            str(draft),
            "--system",
            "你只输出重写后的完整正文，无解释。",
            "--max-tokens",
            str(args.max_tokens),
        ]
        if args.model:
            m_args.extend(["--model", args.model])
        code_m, out_m, err_m = run_py(m_args)
        llm_m = parse_json(out_m)
        if code_m == 0 and llm_m.get("ok") and draft.is_file():
            text2 = strip_em_dashes(
                normalize_h2(strip_fences(draft.read_text(encoding="utf-8", errors="replace")))
            )
            if han_count(text2) >= 80:
                text = text2
                han = han_count(text)
                mind_rewrite = True
                llm = llm_m

    # 最多加厚 4 轮；目标抬到下限的 1.15，避免卡在 1700 附近假完成
    target_han = int(brief_min * 1.15) if brief_min else None
    while target_han and han < target_han and han >= 80 and expand_rounds < 4:
        expand_rounds += 1
        expand_prompt = (
            f"下面是一篇未写够字数的正文（当前约 {han} 汉字，目标至少 {brief_min}，尽量到 {target_han}）。\n"
            "请**加厚同一篇**（优先补场面/查证/反差/口语短锤，禁止空话注水与文青隐喻）。\n"
            "每节须有动作痕迹；结构 `## 一、`…；**禁止破折号**；禁止元话与代码围栏。\n"
            "只输出扩写后的完整正文。\n\n"
            "===== 原文 =====\n"
            f"{text.strip()}\n"
            "===== 合同摘要（勿复述）=====\n"
            f"{body[-2500:]}\n"
        )
        exp_path = run_dir / f"_expand_prompt_{expand_rounds}.md"
        exp_path.write_text(expand_prompt, encoding="utf-8")
        exp_args = [
            str(SCRIPTS / "cliproxy_chat.py"),
            "--prompt",
            str(exp_path),
            "--out",
            str(draft),
            "--system",
            "你只输出扩写后的完整正文，无解释。",
            "--max-tokens",
            str(args.max_tokens),
        ]
        if args.model:
            exp_args.extend(["--model", args.model])
        code_e, out_e, err_e = run_py(exp_args)
        llm_e = parse_json(out_e)
        if code_e == 0 and llm_e.get("ok") and draft.is_file():
            text2 = strip_em_dashes(
                normalize_h2(strip_fences(draft.read_text(encoding="utf-8", errors="replace")))
            )
            h2 = han_count(text2)
            if h2 > han:
                text = text2
                han = h2
                expanded = True
                llm = llm_e
            else:
                break
        else:
            break

    # 终稿再硬清破折号（expand/mind 仍可能带回）
    cleaned = strip_em_dashes(normalize_h2(text))
    if cleaned != text:
        dash_stripped = True
        text = cleaned
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
        "brief_min": brief_min,
        "auto_expanded": expanded,
        "expand_rounds": expand_rounds,
        "mind_rewrite": mind_rewrite,
        "dash_stripped": dash_stripped,
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
