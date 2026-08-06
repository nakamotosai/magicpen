#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""组装写稿提示词 v3.4：mind + 加权 rules + content_ban + 随机槽 + sample(仅笔迹)。"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path


def pick_sample(persona: Path) -> Path:
    for name in ("sample.md", "train.md", "SAMPLE.md"):
        p = persona / name
        if p.exists():
            return p
    raise FileNotFoundError(f"人格包缺 sample.md: {persona}")


def pick_rules(persona: Path) -> Path:
    p = persona / "rules.md"
    if p.exists():
        return p
    raise FileNotFoundError(f"人格包缺 rules.md（请先跑 style_sensors --rules）: {persona}")


def load_text(p: Path) -> str:
    return p.read_text(encoding="utf-8").strip()


def load_optional(persona: Path, names: tuple[str, ...]) -> str:
    for name in names:
        np = persona / name
        if np.exists():
            return load_text(np)
    return ""


def content_ban_block(persona: Path) -> str:
    p = persona / "content_ban.txt"
    if not p.exists():
        return "（无 content_ban.txt；仍禁止复读样本情节。）"
    items = []
    for ln in p.read_text(encoding="utf-8").splitlines():
        s = ln.strip()
        if s and not s.startswith("#"):
            items.append(s)
    if not items:
        return "（禁表空）"
    return "禁止在新文出现（除非 brief 明文要写）：\n- " + "\n- ".join(items[:40])


OPENERS = [
    "从一件刚撞上的具体小事/提问切进（勿用样本同款开场）。",
    "先甩一个现场细节或反差，再亮身份或立场（若 brief 允许第一人称）。",
    "先澄清「别人容易误会的一点」，再进入正题。",
    "用一句读者可能在想的话当靶子，再拆。",
]

METAPHOR_POOLS = [
    "本篇核心喻体自选生活/器物类，避免船/漆/镜/账本（若未被 brief 点名）。",
    "本篇可用身体/天气/交通类喻体；禁用上篇用过的万能政论隐喻套装。",
    "本篇少用长隐喻，多靠场面与动作推进判断。",
    "本篇允许一个主隐喻，但节末短评不得篇篇同构「最怕的是…」。",
]

CLOSE_STYLES = [
    "收束偏劝散/放手：别浪费时间在假议题上。",
    "收束偏点破机制：谁在受益、谁在买单。",
    "收束偏生活继续：一手信息、日子还要过。",
    "收束偏冷一句立住，不解释三行。",
]

ASIDE = [
    "中段可插一句生活岔开再拉回（短）。",
    "本篇少岔开，节奏更紧。",
    "中段用一次「我查了/我看见」动作句。",
    "中段用一次读者口吻的设问短段。",
]


def random_slot(seed: str | None) -> dict:
    if seed:
        rnd = random.Random(int(hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16], 16))
    else:
        rnd = random.Random(time.time_ns())
    slot = {
        "seed": seed or f"t{time.time_ns()}",
        "opener": rnd.choice(OPENERS),
        "metaphor": rnd.choice(METAPHOR_POOLS),
        "close": rnd.choice(CLOSE_STYLES),
        "aside": rnd.choice(ASIDE),
        "must_vary": "开篇句、主隐喻、节末收束句式三者至少两处与「通用政论模板」明显不同。",
    }
    return slot


def metrics_param_block(persona: Path) -> str:
    """把 metrics.json 压成可读参数表（无样本正文时的硬指纹）。"""
    mp = persona / "metrics.json"
    if not mp.exists():
        return "（无 metrics.json）"
    try:
        m = json.loads(mp.read_text(encoding="utf-8"))
    except Exception:
        return "（metrics.json 不可读）"
    keys = [
        ("chars", "样本总字量级"),
        ("sent_count", "句数"),
        ("para_count", "段数"),
        ("sent_len_mean", "句均长"),
        ("sent_len_std", "句长波动"),
        ("para_len_mean", "段均长"),
        ("sents_per_para_mean", "句/段"),
        ("single_sent_para_ratio", "一段一句占比"),
        ("single_sent_line_ratio", "单句行占比"),
        ("dash_per_1k", "破折号/千字"),
        ("punct_density", "标点密度"),
        ("particle_rate", "助词率(口语旁证)"),
        ("ttr", "字种丰富度"),
        ("four_char_density", "四字格密度"),
        ("list_density", "列表行占比"),
        ("ai_tells_per_1k", "AI套话/千字"),
    ]
    lines = ["从原文传感器提炼的数值指纹（**不是**原文；按量级贴，勿复读情节）："]
    for i, (k, label) in enumerate(keys, 1):
        if k in m and m[k] is not None:
            lines.append(f"{i}. {label} ≈ {m[k]}")
    lines.append(
        f"{len(lines)}. 版式目标：空行密；约一半单句成段；句长均值附近波动，禁止句句等长。"
    )
    return "\n".join(lines)


def build(
    persona: Path,
    brief: str,
    genre: str | None,
    seed: str | None = None,
    no_sample: bool = False,
) -> str:
    rules = load_text(pick_rules(persona))
    mind = load_optional(persona, ("mind.md", "MIND.md"))
    pid = persona.name
    genre_line = genre or "跟 brief；未指定则 essay/longform"
    notes = load_optional(persona, ("NOTES.md", "extras.md", "USER.md"))
    slot = random_slot(seed)

    sample_for_prompt = ""
    if not no_sample:
        sample = load_text(pick_sample(persona))
        sample_for_prompt = sample
        if len(sample) > 3500:
            sample_for_prompt = sample[:3500] + "\n…（样本截断；只学笔迹，勿续写后面情节）"

    mode = "params-only（无原文样本）" if no_sample else "mind+rules+sample笔迹"
    parts: list[str] = []
    parts.append(f"# 神笔 · Writer 提示词 v3.4（人格包 `{pid}` · {mode}）\n\n")
    parts.append(
        "你是写稿分身。任务：用这个人的**脑子推进方式 + 笔迹参数**写【新文任务】。\n"
        "不是润色 brief，不是摘要原文，不是复读样本故事，不是通用「鲁迅式政论」。\n\n"
    )
    parts.append("## 0. 铁律（P0）\n\n")
    if no_sample:
        parts.append(
            "1. **mind.md = 怎么想**（若有）：按步骤推进判断；可换事实，不换脑回路。\n"
            "2. **rules = 加权笔迹**：P0 违反 = 失败；P1 节奏；P2 表层。\n"
            "3. **本模式无原文样本**：只靠 rules + metrics 数值指纹 + mind；禁止脑补样本情节。\n"
            "4. **content_ban = 硬禁**：样本事件与招牌禁止进新文（除非 brief 明文）。\n"
            "5. **brief = 当次唯一事实源**（人称、结构、题材、长度）。\n"
            "6. **随机槽必须落地**：见随机槽节；禁止四篇同构万能稿。\n"
            "7. 只输出新文正文（除非 brief 要标题）。\n"
        )
    else:
        parts.append(
            "1. **mind.md = 怎么想**（若有）：按步骤推进判断；可换事实，不换脑回路。\n"
            "2. **rules = 加权笔迹**：P0 违反 = 失败；P1 节奏；P2 表层。\n"
            "3. **sample = 仅笔迹参考**（句段、空行、口气）——**不是**情节/开场/专名素材库。\n"
            "4. **content_ban = 硬禁**：样本事件与招牌禁止进新文（除非 brief 明文）。\n"
            "5. **brief = 当次唯一事实源**（人称、结构、题材、长度）。\n"
            "6. **随机槽必须落地**：见第 6 节；禁止四篇同构万能稿。\n"
            "7. 只输出新文正文（除非 brief 要标题）。\n"
        )

    if mind:
        parts.append("\n## 1. 思维链 mind.md（**最高优先 · 怎么想**）\n\n")
        parts.append(mind)
        parts.append("\n")
    else:
        parts.append(
            "\n## 1. 思维链\n\n"
            "（人格包无 mind.md）仍须：刺激→查证/场面→反差→判断→短收束；"
            "禁止开篇就升华。\n"
        )

    parts.append("\n## 2. 写作要领 rules（加权 · 从原文提炼）\n\n")
    parts.append(rules)

    parts.append("\n\n## 3. 内容禁表 content_ban\n\n")
    parts.append(content_ban_block(persona))

    if no_sample:
        parts.append("\n\n## 4. 数值指纹 metrics（从原文传感器提炼 · **无正文**）\n\n")
        parts.append(metrics_param_block(persona))
        parts.append(
            "\n\n> 本跑**不提供**原文段落。禁止凭记忆复述样本事件/开场；"
            "布局与口气只跟 rules + 上表量级。\n"
        )
    else:
        parts.append("\n\n## 4. 原文样本（**仅笔迹** · 禁止当情节库）\n\n```text\n")
        parts.append(sample_for_prompt)
        parts.append(
            "\n```\n\n"
            "> 换行与分段是笔迹。**禁止**把样本谁在说话、去过哪、辟过什么谣、认识谁，"
            "写进新文当默认开场或论据。\n"
        )

    parts.append(f"\n## 5. 体裁\n\n{genre_line}\n")
    if notes:
        parts.append("\n## 5b. 人格包备注\n\n")
        parts.append(notes)
        parts.append("\n")

    parts.append("\n## 6. 本跑随机槽（必须遵守 · 增加篇间差异）\n\n")
    parts.append(f"- seed: `{slot['seed']}`\n")
    parts.append(f"- 开篇策略: {slot['opener']}\n")
    parts.append(f"- 隐喻策略: {slot['metaphor']}\n")
    parts.append(f"- 收束策略: {slot['close']}\n")
    parts.append(f"- 中段: {slot['aside']}\n")
    parts.append(f"- 差异硬要求: {slot['must_vary']}\n")

    parts.append("\n## 7. 新文任务与用户条件（唯一事实源）\n\n")
    parts.append(brief.strip())
    parts.append(
        "\n\n## 8. 输出前自检（v3.5）\n\n"
        "- [ ] 是否按 mind 步骤走过（不是只堆结论）\n"
        "- [ ] 开篇是否刺激→查证→反差，而非总判金句起手\n"
        "- [ ] **每一编号节**是否有场面/查证动作（翻/查/群/答弁/现场），非纯履历提纲\n"
        "- [ ] 空行/口气是否贴 rules+sample（不是像别的人格）\n"
        "- [ ] content_ban 是否零命中\n"
        "- [ ] 随机槽开篇/隐喻/收束是否落地\n"
        "- [ ] 有无「最怕的是…/不是草包所以…」万能句刷屏\n"
        "- [ ] 节题是否自拟（未焊死船/漆/镜/账本万能套）\n\n"
        "只写新文正文。\n"
    )
    return "".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True, help="人格包目录")
    ap.add_argument("--brief", type=Path)
    ap.add_argument("--brief-text", type=str)
    ap.add_argument("--genre", type=str, default=None)
    ap.add_argument("--seed", type=str, default=None, help="随机槽种子；同 seed 可复现")
    ap.add_argument(
        "--no-sample",
        action="store_true",
        help="不注入原文 sample，只给 mind+rules+metrics+content_ban+brief",
    )
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--voice", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.voice is not None:
        print(json.dumps({"ok": False, "error": "removed: use --persona only"}, ensure_ascii=False), file=sys.stderr)
        return 2

    if args.brief_text:
        brief = args.brief_text
    elif args.brief:
        brief = args.brief.read_text(encoding="utf-8")
    else:
        print("need --brief or --brief-text", file=sys.stderr)
        return 2

    try:
        text = build(
            args.persona.resolve(),
            brief,
            args.genre,
            args.seed,
            no_sample=bool(args.no_sample),
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(text, encoding="utf-8")
    print(
        json.dumps(
            {
                "ok": True,
                "out": str(args.out),
                "chars": len(text),
                "persona": str(args.persona),
                "no_sample": bool(args.no_sample),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
