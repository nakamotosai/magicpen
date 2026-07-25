#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""卡卡西 · 风格传感器。

主产物：**rules.md**（约 20 条一行一句写作指令，直接进提示词）。
旁产物：**metrics.json**（机器硬分用，不进 Writer 主路径）。

用法：
  pythonw style_sensors.py --text sample.md --rules rules.md --metrics metrics.json
  pythonw style_sensors.py --text draft.md --metrics-ref metrics.json --metrics draft_metrics.json
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

VERSION = "0.5.2"

AI_TELLS = [
    r"综上所述",
    r"总而言之",
    r"值得注意的是",
    r"不可否认",
    r"在当今时代",
    r"赋能",
    r"抓手",
    r"闭环",
    r"底层逻辑",
    r"首先[，,].*其次",
    r"不仅[^。]{0,20}而且",
]

PARTICLES = list("的了吗呢吧啊呀嘛啦着过")


def read_text(path: Path | None, raw: str | None) -> str:
    if raw is not None:
        return raw
    if path is None:
        raise SystemExit("need --text or --stdin")
    return path.read_text(encoding="utf-8")


def split_sents(text: str) -> list[str]:
    parts = re.split(r"(?<=[。！？!?；;])\s*", text.strip())
    return [p for p in parts if p.strip()]


def split_paras(text: str) -> list[str]:
    """切段：优先空行；中文散文常「单换行即段」且无空行，需回退。

    回退规则（仅当空行切段数 ≤1 且正文多行时）：
    - 每个非空行若以句末标点结束，视为一段；
    - 否则把连续非空行粘成一段（兼容软折行）。
    """
    t = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    blank = [p.strip() for p in re.split(r"\n\s*\n+", t) if p.strip()]
    lines = [ln.strip() for ln in t.split("\n") if ln.strip()]
    if len(blank) >= 2:
        return blank
    if len(lines) <= 1:
        return blank or lines or []

    # 空行切不出段：用「行≈段」启发式（中文原著常见）
    end_re = re.compile(r"[。！？!?…」』》】）)]\s*$")
    paras: list[str] = []
    buf: list[str] = []
    for ln in lines:
        if end_re.search(ln) and not buf:
            paras.append(ln)
        elif end_re.search(ln) and buf:
            buf.append(ln)
            paras.append("".join(buf) if all(len(x) < 40 for x in buf) else "\n".join(buf))
            buf = []
        else:
            # 行末无句点：可能是软折行
            buf.append(ln)
            # 若缓冲已像完整句群，且下一逻辑靠长度收束
            joined = "".join(buf)
            if end_re.search(joined) and char_count(joined) >= 40:
                paras.append(joined)
                buf = []
    if buf:
        paras.append("\n".join(buf) if len(buf) > 1 else buf[0])
    # 仍异常：至少按行切，避免 para_count=1 毒死 rules
    if len(paras) <= 1 and len(lines) >= 3:
        return lines
    return paras or blank or lines


def char_count(text: str) -> int:
    return len(re.sub(r"\s+", "", text))


def mean_std(nums: list[float]) -> tuple[float, float]:
    if not nums:
        return 0.0, 0.0
    m = sum(nums) / len(nums)
    if len(nums) == 1:
        return m, 0.0
    v = sum((x - m) ** 2 for x in nums) / len(nums)
    return m, math.sqrt(v)


def ttr(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    return len(set(chars)) / len(chars)


def particle_rate(text: str) -> float:
    chars = [c for c in text if not c.isspace()]
    if not chars:
        return 0.0
    hits = sum(1 for c in chars if c in PARTICLES)
    return hits / len(chars)


def dash_per_1k(text: str) -> float:
    n = char_count(text)
    if n == 0:
        return 0.0
    dashes = text.count("——") + text.count("—") + text.count("–")
    return dashes * 1000.0 / n


def punct_density(text: str) -> float:
    n = char_count(text)
    if n == 0:
        return 0.0
    punct = len(re.findall(r"[，。！？、；：,.!?;:\"'（）()【】\[\]《》]", text))
    return punct / n


def ai_tells(text: str) -> list[str]:
    hits = []
    for pat in AI_TELLS:
        if re.search(pat, text):
            hits.append(pat)
    return hits


def four_char_density(text: str) -> float:
    blocks = re.findall(r"[一-鿿]{4}", text)
    n = char_count(text)
    if n == 0:
        return 0.0
    return len(blocks) * 4 / n


def list_density(text: str) -> float:
    lines = text.splitlines()
    if not lines:
        return 0.0
    bullets = sum(1 for ln in lines if re.match(r"^\s*([-*•]|\d+[\.\)])\s+", ln))
    return bullets / max(len(lines), 1)


def layout_metrics(text: str) -> dict:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    paras = split_paras(text)
    end_sent = re.compile(r"[。！？!?…]$")
    single_sent_lines = 0
    multi_sent_lines = 0
    sents_per_line: list[int] = []
    for ln in lines:
        parts = [x for x in re.split(r"(?<=[。！？!?])\s*", ln) if x.strip()]
        sc = len(parts) if parts else (1 if ln else 0)
        sents_per_line.append(sc)
        if sc <= 1 and (end_sent.search(ln) or sc == 1):
            single_sent_lines += 1
        if sc > 1:
            multi_sent_lines += 1
    sents_per_para: list[int] = []
    for p in paras:
        parts = [x for x in re.split(r"(?<=[。！？!?])\s*", p) if x.strip()]
        sents_per_para.append(len(parts) if parts else 1)
    n_lines = max(len(lines), 1)
    n_paras = max(len(paras), 1)
    single_para = sum(1 for n in sents_per_para if n == 1)
    return {
        "line_count": len(lines),
        "single_sent_line_ratio": round(single_sent_lines / n_lines, 4),
        "multi_sent_line_ratio": round(multi_sent_lines / n_lines, 4),
        "sents_per_line_mean": round(sum(sents_per_line) / n_lines, 3) if lines else 0.0,
        "sents_per_para_mean": round(sum(sents_per_para) / n_paras, 3) if paras else 0.0,
        "single_sent_para_ratio": round(single_para / n_paras, 4) if paras else 0.0,
        "para_len_mean": round(sum(char_count(p) for p in paras) / n_paras, 3) if paras else 0.0,
    }


def features(text: str) -> dict:
    sents = split_sents(text)
    paras = split_paras(text)
    sent_lens = [char_count(s) for s in sents] or [0.0]
    para_lens = [char_count(p) for p in paras] or [0.0]
    sm, ss = mean_std([float(x) for x in sent_lens])
    pm, ps = mean_std([float(x) for x in para_lens])
    n = char_count(text)
    tells = ai_tells(text)
    lay = layout_metrics(text)
    return {
        "chars": n,
        "sent_count": len(sents),
        "para_count": len(paras),
        "sent_len_mean": round(sm, 3),
        "sent_len_std": round(ss, 3),
        "para_len_mean": round(pm, 3),
        "para_len_std": round(ps, 3),
        "dash_per_1k": round(dash_per_1k(text), 3),
        "punct_density": round(punct_density(text), 4),
        "ttr": round(ttr(text), 4),
        "particle_rate": round(particle_rate(text), 4),
        "four_char_density": round(four_char_density(text), 4),
        "list_density": round(list_density(text), 4),
        "ai_tells_hits": tells,
        "ai_tells_per_1k": round(len(tells) * 1000.0 / n, 3) if n else 0.0,
        **lay,
        "version": VERSION,
    }


def rel_err(a: float, b: float) -> float:
    if b == 0:
        return 0.0 if a == 0 else 1.0
    return abs(a - b) / abs(b)


def rules_md_lines(feat: dict) -> list[str]:
    """固定约 20 条：一行一句，直接可贴进提示词。"""
    spp = float(feat.get("sents_per_para_mean") or 0)
    ssl = float(feat.get("single_sent_line_ratio") or 0)
    msl = float(feat.get("multi_sent_line_ratio") or 0)
    spl = float(feat.get("sents_per_line_mean") or 0)
    sm = float(feat.get("sent_len_mean") or 0)
    ss = float(feat.get("sent_len_std") or 0)
    plm = float(feat.get("para_len_mean") or 0)
    pls = float(feat.get("para_len_std") or 0)
    dash = float(feat.get("dash_per_1k") or 0)
    punct = float(feat.get("punct_density") or 0)
    ttr_v = float(feat.get("ttr") or 0)
    pr = float(feat.get("particle_rate") or 0)
    fcd = float(feat.get("four_char_density") or 0)
    ld = float(feat.get("list_density") or 0)
    ai = float(feat.get("ai_tells_per_1k") or 0)
    sspr = float(feat.get("single_sent_para_ratio") or 0)
    sc = int(feat.get("sent_count") or 0)
    pc = int(feat.get("para_count") or 0)
    chars = int(feat.get("chars") or 0)

    if dash <= 0.5:
        dash_line = "破折号几乎不用；不要为了「文青感」乱加破折。"
    elif dash <= 3.0:
        dash_line = f"破折号很少（约 {dash:.1f}/千字）；可偶用，勿刷屏。"
    elif dash <= 10.0:
        dash_line = f"破折号有一定出现（约 {dash:.1f}/千字）；跟样本频率，勿归零也勿翻倍。"
    else:
        dash_line = f"破折号较密（约 {dash:.1f}/千字）；仿写允许破折，但勿句句都有。"

    if ssl >= 0.55:
        layout_line = "样本一行一句偏多；仿写可短行，但仍要有完整段落感，禁止整页比样本更碎。"
    else:
        layout_line = "禁止一行一句铺满全篇；多句应落在同一段落里，换行跟样本段落节奏。"

    # 极端布局：不写「每段 69 句」这种毒指令
    if pc <= 1 and sc >= 8:
        para_line = (
            "样本分段信号弱（几乎被识别成整篇一段）；仿写请按语义自然分段，"
            "禁止整篇一段墙，也禁止一行一句电报体。"
        )
        para_len_line = (
            "不要把「整篇字数」当成「每段必须写满」；按场面切段，段长可长短交错。"
        )
        spp_line = "段落里多句推进；关键处同段多句，勿全篇口号体，也勿合成超长演讲段。"
    else:
        para_line = f"样本约 {pc} 段；仿写分段密度跟样本，勿无故砍成碎卡片或合成一段墙。"
        para_len_line = (
            f"段落体量大约每段 {plm:.0f} 字量级（波动约 {pls:.0f}）；"
            "勿切成碎卡片，也勿整篇一大坨。"
        )
        if spp >= 25:
            spp_line = (
                f"样本段内句子偏多（约 {spp:.0f} 句/段量级）；可写密实段，"
                "但新文仍应按语义换段，禁止为凑数合成巨型段。"
            )
        else:
            spp_line = f"每段大约 {spp:.1f} 句；不要整篇一段一句，也不要一段写成长篇演讲。"

    lines = [
        f"样本体量约 {chars} 字、{sc} 句、{pc} 段；新文长短听用户任务，笔迹密度跟样本。",
        f"句子长短跟样本：句长均值约 {sm:.0f} 字，可有起伏（标准差约 {ss:.0f}）；避免句句等长排比。",
        spp_line,
        para_len_line if pc > 1 or sc < 8 else para_line,
        layout_line,
        f"一行多句占比约 {msl:.0%}；能同段写完的意思不要拆成电报行。",
        f"行均约 {spl:.1f} 句；保持可读的行内节奏，不要机械断行。",
        f"一段一句占比约 {sspr:.0%}；关键推进处应有多句同段，避免全篇口号体。"
        if sspr < 0.6
        else f"样本一段一句偏多（约 {sspr:.0%}）；仿写可短段，但关键处仍应有多句推进。",
        dash_line,
        f"标点疏密跟样本（密度约 {punct:.2f} 量级）；不要忽然英文腔或整段无标点。",
        "用词面跟样本量级；不要说明书腔、词典堆砌，也别为「像文青」硬堆成语。",
        f"语气助词冷热跟样本（约 {pr:.2f} 量级）；勿忽然口语注水或忽然文言。",
        "四字格/成语点到为止；别为了「有文采」刷屏。",
        (
            "样本几乎不用条目列表，仿写也少用 1.2.3. 排比清单。"
            if ld < 0.08
            else "样本有一定列表感，可用短列，但勿做成 PPT 提纲体。"
        ),
        (
            "禁止「综上所述 / 赋能 / 闭环 / 值得注意的是」等套话；样本没有就更不能加。"
            if ai <= 0.5
            else "样本偶有套话痕迹；仿写仍应压低空话，宁冷勿油。"
        ),
        (
            "学的是笔迹与节奏（句长、段法、冷热、收束），不是样本角色/身份/物种/世界观；"
            "禁止把叙事者壳、样本专名职业搬进新文，除非 brief 明文要求角色仿写。"
        ),
        "原文换行与分段是笔迹的一部分；多句同段就同段，不要自行改成一行一句。",
        "反讽与判断尽量从动作、场面长出，少用「我明白了」后整段主题演讲。",
        "新文事实、人称、题材只听 brief；样本只供笔迹；禁止用样本情节/道具/配角当默认主角设定。",
        "只输出新文正文（除非任务要求标题）；写完自检：布局句长 + 是否误带样本身份壳。",
    ]
    # 保证正好 20 条
    assert len(lines) == 20, len(lines)
    return lines


def write_rules_md(path: Path, feat: dict) -> str:
    lines = rules_md_lines(feat)
    body = ["# 写作要领 · rules", "", f"_sensor {VERSION}_", ""]
    for i, line in enumerate(lines, 1):
        body.append(f"{i}. {line}")
    body.append("")
    text = "\n".join(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def score_vs_metrics(feat: dict, anchor: dict) -> float:
    # metrics.json 可能包在 {"metrics":{}} 或扁平
    if "metrics" in anchor and isinstance(anchor["metrics"], dict):
        anchor = {**anchor["metrics"], **{k: v for k, v in anchor.items() if k != "metrics"}}
    parts = []
    parts.append(max(0.0, 1.0 - rel_err(feat["sent_len_mean"], anchor.get("sent_len_mean", feat["sent_len_mean"])) / 0.15))
    parts.append(max(0.0, 1.0 - rel_err(feat["sent_len_std"], anchor.get("sent_len_std", feat["sent_len_std"] or 1)) / 0.25))
    ad = float(anchor.get("dash_per_1k", 0) or 0)
    fd = float(feat.get("dash_per_1k", 0) or 0)
    if ad <= 0.05:
        parts.append(1.0 if fd <= 0.5 else max(0.0, 1.0 - (fd - 0.5) / 5.0))
    else:
        ratio = fd / ad if ad else 1.0
        if 0.5 <= ratio <= 1.5:
            parts.append(1.0)
        else:
            parts.append(max(0.0, 1.0 - abs(ratio - 1.0)))
    parts.append(max(0.0, 1.0 - rel_err(feat["ttr"], anchor.get("ttr", feat["ttr"])) / 0.20))
    parts.append(max(0.0, 1.0 - rel_err(feat["particle_rate"], anchor.get("particle_rate", feat["particle_rate"])) / 0.25))
    fp = feat["ai_tells_per_1k"]
    if fp == 0:
        parts.append(1.0)
    elif fp <= 0.5:
        parts.append(0.7)
    else:
        parts.append(0.0)
    ar = float(anchor.get("single_sent_line_ratio", 0.35) or 0.35)
    fr = float(feat.get("single_sent_line_ratio", ar) or ar)
    if fr <= ar + 0.15:
        parts.append(1.0)
    elif fr <= ar + 0.35:
        parts.append(0.5)
    else:
        parts.append(max(0.0, 1.0 - (fr - ar) / 0.6))
    aspp = float(anchor.get("sents_per_para_mean", 2.0) or 2.0)
    fspp = float(feat.get("sents_per_para_mean", aspp) or aspp)
    if aspp > 0 and 0.5 <= (fspp / aspp) <= 1.8:
        parts.append(1.0)
    else:
        parts.append(max(0.0, 1.0 - abs((fspp / aspp) if aspp else 1.0 - 1.0)))
    return round(sum(parts) / len(parts), 4)


def main() -> int:
    ap = argparse.ArgumentParser(description="kakashi style sensors → rules.md + metrics.json")
    ap.add_argument("--text", type=Path, help="input text file")
    ap.add_argument("--stdin", action="store_true")
    ap.add_argument("--rules", type=Path, help="写出 rules.md（主产物）")
    ap.add_argument("--metrics", type=Path, help="写出 metrics.json（硬分旁证）")
    ap.add_argument("--metrics-ref", type=Path, help="对照用 metrics.json，算 score_vs_anchor")
    ap.add_argument("--min-chars", type=int, default=200)
    # 禁止旧参数：若有人传 --out/--anchor 明确报错
    ap.add_argument("--out", type=Path, help=argparse.SUPPRESS)
    ap.add_argument("--anchor", type=Path, help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.out or args.anchor:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": "removed: use --rules rules.md and/or --metrics metrics.json; score with --metrics-ref",
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2

    try:
        raw = sys.stdin.read() if args.stdin else None
        text = read_text(args.text, raw)
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 3

    feat = features(text)
    code = 0
    if feat["chars"] < args.min_chars:
        feat["error"] = f"too_short chars={feat['chars']} min={args.min_chars}"
        code = 2

    if args.metrics_ref and args.metrics_ref.exists():
        ref = json.loads(args.metrics_ref.read_text(encoding="utf-8"))
        feat["score_vs_anchor"] = score_vs_metrics(feat, ref)
    else:
        feat["score_vs_anchor"] = None

    rules_text = None
    if args.rules:
        rules_text = write_rules_md(args.rules, feat)

    if args.metrics:
        args.metrics.parent.mkdir(parents=True, exist_ok=True)
        args.metrics.write_text(json.dumps(feat, ensure_ascii=False, indent=2), encoding="utf-8")

    # stdout：简报
    print(
        json.dumps(
            {
                "ok": code == 0,
                "version": VERSION,
                "chars": feat.get("chars"),
                "rules": str(args.rules) if args.rules else None,
                "metrics": str(args.metrics) if args.metrics else None,
                "score_vs_anchor": feat.get("score_vs_anchor"),
                "rules_lines": 20 if rules_text else None,
                "error": feat.get("error"),
            },
            ensure_ascii=False,
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
