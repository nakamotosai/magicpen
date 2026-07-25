#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从长样本硬截断/抽选 train 窗（工厂 Phase0）。

默认目标窗由 SKILL 字数合同驱动；本脚本只做可复现截取，不评分。
策略：
  head   — 从文首按汉字截到 target（**完整段落**边界）
  body   — 跳过前 skip_han 后截（跳过序/编者按）
  mid    — 从全文中部起截
  spread — 头/中/尾各取约 target/3 拼成窗（去重段落）

截断优先级：完整段落（空行分隔）→ 单段过长时退回句号 → 硬切。
写时 few-shot 仍走 corpus 1–2 段，本脚本输出的是 **工厂 train 窗**。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


def han_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def split_paras(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]


def take_han_sentence(text: str, n: int) -> str:
    """句号对齐截断（仅当单段过长、无法完整段装下时退路）。"""
    out: list[str] = []
    c = 0
    for ch in text:
        out.append(ch)
        if "一" <= ch <= "鿿":
            c += 1
        if c >= n:
            break
    s = "".join(out)
    for i in range(len(s) - 1, max(0, len(s) - 120), -1):
        if s[i] in "。！？!?":
            s = s[: i + 1]
            break
    return s.strip()


def take_han(text: str, n: int, max_han: int | None = None) -> str:
    """按汉字目标截取，**优先在完整段落边界结束**。

    - 累加完整段落，直到再加下一段会超过 target
    - 若当前累计为 0 且首段 ≤ max_han：整段收下（可略超 target，不半段）
    - 若首段 > max_han：段内退回句号对齐，再保证 ≤ max_han
    - 若已有完整段且下一段会使总量 ≤ max_han、且当前 < min(n, 0.7*n 附近不足)：
      仍优先停在段界（不半段）；略少优于半段
    """
    if n <= 0:
        return ""
    cap = max_han if max_han is not None else max(n, n)
    total_src = han_count(text)
    if total_src <= n:
        return text.strip()

    paras = split_paras(text)
    if not paras:
        s = take_han_sentence(text, n)
        if max_han is not None and han_count(s) > max_han:
            s = take_han_sentence(text, max_han)
        return s

    # 单段（无空行结构）：尽量句号对齐
    if len(paras) == 1:
        s = take_han_sentence(paras[0], n)
        if max_han is not None and han_count(s) > max_han:
            s = take_han_sentence(paras[0], max_han)
        return s

    out_parts: list[str] = []
    total = 0
    for p in paras:
        ph = han_count(p)
        if total + ph <= n:
            out_parts.append(p)
            total += ph
            continue
        # 再加本段会超 target
        if not out_parts:
            # 必须至少拿一段：整段若 ≤cap 则整段；否则段内句号截
            if ph <= cap:
                out_parts.append(p)
                total += ph
            else:
                s = take_han_sentence(p, min(n, cap))
                if han_count(s) == 0:
                    s = take_han_sentence(p, cap)
                out_parts.append(s)
                total = han_count(s)
        else:
            # 已有完整段：默认停在段界（不半段）
            # 若当前过短（< 0.55*target）且整段装入仍 ≤cap，则收下整段（略超 target 可）
            if total < int(n * 0.55) and total + ph <= cap:
                out_parts.append(p)
                total += ph
            # else: stop at previous paragraph boundary
        break

    joined = "\n\n".join(out_parts).strip()
    if max_han is not None and han_count(joined) > max_han:
        # 极端：多段拼超 cap，回退逐段重装
        out_parts2: list[str] = []
        t2 = 0
        for p in out_parts:
            ph = han_count(p)
            if t2 + ph <= max_han:
                out_parts2.append(p)
                t2 += ph
            else:
                break
        joined = "\n\n".join(out_parts2).strip() or take_han_sentence(text, max_han)
    return joined


def skip_han(text: str, n: int) -> str:
    if n <= 0:
        return text
    c = 0
    for i, ch in enumerate(text):
        if "一" <= ch <= "鿿":
            c += 1
        if c >= n:
            # 尽量从下一段起，避免半段开头
            rest = text[i + 1 :]
            # 若落在段中，跳到下一个空行后
            m = re.search(r"\n\s*\n+", rest)
            if m and han_count(rest[m.end() :]) >= 50:
                return rest[m.end() :]
            return rest
    return text


def spread_take(text: str, n: int, max_han: int | None = None) -> str:
    total = han_count(text)
    if total <= n:
        return text.strip()
    part = max(40, n // 3)
    head = take_han(text, part, max_han=max_han)
    mid = take_han(skip_han(text, max(0, total // 2 - part // 2)), part, max_han=max_han)
    tail = take_han(skip_han(text, max(0, total - part - 20)), part, max_han=max_han)
    chunks: list[str] = []
    for c in (head, mid, tail):
        if c and c not in chunks:
            chunks.append(c)
    joined = "\n\n".join(chunks)
    if han_count(joined) > n + 80:
        joined = take_han(joined, n, max_han=max_han)
    return joined.strip()


def ends_on_paragraph_boundary(source: str, out: str) -> bool:
    """out 是否停在 source 的完整段落末尾（或全文末）。"""
    if not out:
        return False
    src = source.replace("\r\n", "\n")
    o = out.replace("\r\n", "\n").strip()
    if src.strip() == o:
        return True
    # out 对应 src 前缀（允许尾空白）
    idx = src.find(o)
    if idx < 0:
        # 可能由 spread 拼接，检查每段是否完整
        for p in split_paras(o):
            if p not in src:
                return False
        return True
    after = src[idx + len(o) :].lstrip()
    if not after:
        return True
    # 下一段应以段落分隔开始，或 out 末段是完整段
    # 若 after 紧接非空白且无先空行，则可能半段
    # 找 out 在 src 中结束后，是否处于 \n\n 边界
    end = idx + len(o)
    # 向后看：若紧跟内容前有 \n\n，或 end 已在段末
    tail = src[end:]
    if re.match(r"\s*\n\s*\n", tail) or re.match(r"\s*$", tail):
        return True
    # out 末尾段落是否等于 src 中某完整段
    last = split_paras(o)[-1] if split_paras(o) else o
    return last in split_paras(src)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="kakashi train window cutter — complete-paragraph boundaries"
    )
    ap.add_argument("--sample", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--target", type=int, default=2000, help="默认截到 ≤2000 完整段（v3）")
    ap.add_argument("--min", type=int, default=500, help="硬底 500；完整段落")
    ap.add_argument("--max", type=int, default=3000, help="硬顶 3000；再长必须截")
    ap.add_argument(
        "--strategy",
        choices=["head", "body", "mid", "spread"],
        default="body",
        help="body=跳过 skip_han 后截（默认跳过序）",
    )
    ap.add_argument("--skip-han", type=int, default=0, help="body 策略跳过的汉字数")
    ap.add_argument("--json-meta", type=Path)
    # 拒绝旧 --voice（不应出现在本脚本，防误用）
    ap.add_argument("--voice", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()
    if args.voice is not None:
        print(json.dumps({"ok": False, "error": "removed: cut_train_window has no --voice"}, ensure_ascii=False), file=sys.stderr)
        return 2

    text = args.sample.read_text(encoding="utf-8")
    target = max(args.min, min(args.max, args.target))
    max_han = args.max

    if args.strategy == "head":
        out = take_han(text, target, max_han=max_han)
    elif args.strategy == "body":
        out = take_han(skip_han(text, args.skip_han), target, max_han=max_han)
    elif args.strategy == "mid":
        out = take_han(skip_han(text, max(0, han_count(text) // 3)), target, max_han=max_han)
    else:
        out = spread_take(text, target, max_han=max_han)

    # 底线：若源文够长但截后 < min，尽量再多取完整段
    if han_count(out) < args.min and han_count(text) >= args.min:
        out2 = take_han(text, args.min, max_han=max_han)
        if han_count(out2) >= han_count(out):
            out = out2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(out + "\n", encoding="utf-8")
    meta = {
        "source": str(args.sample),
        "strategy": args.strategy,
        "target": target,
        "han": han_count(out),
        "skip_han": args.skip_han,
        "source_han": han_count(text),
        "para_count": len(split_paras(out)),
        "ends_on_paragraph": ends_on_paragraph_boundary(text if args.strategy == "head" else text, out),
        "boundary": "complete_paragraph",
    }
    if args.json_meta:
        args.json_meta.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(meta, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
