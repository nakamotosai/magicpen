#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 sample 抽 mind.md + content_ban.txt（v3.4 灵魂层）。"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def load_sample(persona: Path) -> str:
    for n in ("sample.md", "train.md", "SAMPLE.md"):
        p = persona / n
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError(f"no sample in {persona}")


def extract_content_bans(text: str) -> list[str]:
    """只收「事件/地点/媒体/产品」级专名，不收半截短语。"""
    bans: list[str] = []

    for m in re.finditer(r"《([^》]{2,20})》", text):
        bans.append(m.group(1))

    # 山/湖/岛 完整地名
    for m in re.finditer(r"([一-鿿]{2,6}(?:山|湖|岛|火山))", text):
        bans.append(m.group(1))

    # 显式白名单式抽取：富士山、樱岛、河口湖、鹿儿岛…
    for tok in (
        "富士山",
        "樱岛",
        "河口湖",
        "鹿儿岛",
        "马尔代夫",
        "假装在东京",
        "時事ドットコム",
        "共同社",
        "日经",
        "朝日",
        "jijicom",
        "参议院选举",
        "世界遗产",
    ):
        if tok in text:
            bans.append(tok)

    # 英文专名（媒体/品牌）
    for m in re.finditer(r"\b([A-Z][a-zA-Z]{3,}(?:\s+[A-Z][a-zA-Z]+)?)\b", text):
        bans.append(m.group(1))

    # 去噪
    stop = {
        "中国", "日本", "东京", "国内", "朋友", "孩子", "新闻", "今天", "我们",
        "什么", "一个", "这个", "自己", "他们", "因为", "所以", "妈妈", "家长",
        "关注重心放到目前已经",  # 半截
    }
    out, seen = [], set()
    for b in bans:
        b = b.strip()
        if len(b) < 2 or b in stop or b in seen:
            continue
        # 拒半截：以说/的/连/一下 等开头
        if re.match(r"^(说|的|连|一下|原来|针对|直播|也去|孩子|记是|话说|我说)", b):
            continue
        if len(b) > 12:
            continue
        seen.add(b)
        out.append(b)
    return out[:40]


def heuristic_mind(text: str, persona_id: str) -> str:
    paras = [p.strip() for p in re.split(r"\n\s*\n+", text) if p.strip()]
    n = len(paras)
    has_first = bool(re.search(r"我是|大家好|我\b", text[:120]))
    has_search = bool(re.search(r"打开|搜索|搜|查|确认|找不到|原文", text))
    has_contrast = bool(re.search(r"然而|但是|可是|反而|满脸|好家伙", text))
    has_life = bool(re.search(r"女儿|晾衣服|生活|幼儿园|周末", text))
    oral = bool(re.search(r"好家伙|满脸问号|散了吧|洗洗睡|咯|啊？", text))
    blank_heavy = text.count("\n\n") >= max(3, n // 2)

    lines = [
        f"# 思维链 · mind（persona `{persona_id}`）",
        "",
        "> 可迁移的「怎么想」。写新题换事实，不换脑回路。禁止把下列步骤写成样本事件复述。",
        "",
        "## 叙事身份（可迁移）",
        (
            "- 第一人称在场：需要时先轻轻点「我是谁/我在哪」，再进题；点名即可，勿每篇复制同款自我介绍长段。"
            if has_first
            else "- 人称跟 brief；勿强行加「大家好我是…」。"
        ),
        "",
        "## 判断怎么长出来（核心 · 按序）",
        "1. **撞上刺激**：私聊/热搜/读者问/标题党 → 先有具体触发，不先升华。",
        (
            "2. **自己去查**：多源确认；写清查了什么、原文侧有没有热度。"
            if has_search
            else "2. **先观察场面**：可见细节代替空论。"
        ),
        (
            "3. **反差落地**：两侧温度差（冷 vs 热、真 vs 读歪），判断从反差长出。"
            if has_contrast
            else "3. **对照再判**：别人说法 vs 我看见的。"
        ),
        (
            "4. **生活短岔开再拉回**（可选、要短）。"
            if has_life
            else "4. **可有轻岔开**；非必须。"
        ),
        "5. **短收束**：劝散 / 点破机制 / 生活继续，三选一；禁止主题演讲三段。",
        "",
        "## 节奏指纹（高权重）",
        f"- 空行：{'密，意群空行是指纹' if blank_heavy else '跟样本'}。",
        f"- 口气：{'口语在场，短锤+问号可独立成段' if oral else '偏冷，勿忽然网感'}。",
        "- 先动作后判断；禁止「我明白了」后整段升华。",
        "",
        "## 绝对不做",
        "- 不把样本事件当万能开场（见 content_ban）。",
        "- 不学身份壳；只学推进与口气。",
        "- 不把 brief 当提纲朗读，不写鲁迅式宣言连发（除非人格本就如此）。",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument("--llm", action="store_true", help="reserved; heuristic is SSOT for stability")
    args = ap.parse_args()
    persona = args.persona.resolve()
    sample = load_sample(persona)
    bans = extract_content_bans(sample)
    mind = heuristic_mind(sample, persona.name)

    ban_path = persona / "content_ban.txt"
    ban_path.write_text(
        "# 样本内容禁表（新文禁止复读事件/专名/招牌）\n"
        "# 一行一项；风格可学，情节不可搬\n"
        + "\n".join(bans)
        + "\n",
        encoding="utf-8",
    )
    mind_path = persona / "mind.md"
    mind_path.write_text(mind.rstrip() + "\n", encoding="utf-8")

    assert mind_path.exists(), "mind not written"
    assert ban_path.exists(), "ban not written"

    print(
        json.dumps(
            {
                "ok": True,
                "mind": str(mind_path),
                "content_ban": str(ban_path),
                "ban_count": len(bans),
                "bans": bans,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
