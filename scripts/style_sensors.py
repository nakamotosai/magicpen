#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""神笔 · 风格传感器。

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

VERSION = "0.6.0-soul"  # v3.4: weighted rules + mind pointer

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


def rules_md_lines(feat: dict) -> list[tuple[str, str]]:
    """加权 rules：返回 (weight, line)。P0 灵魂/布局 > P1 节奏 > P2 表层计量。

    不再假装 20 条等权。条数可变（约 16–18）。
    """
    spp = float(feat.get("sents_per_para_mean") or 0)
    ssl = float(feat.get("single_sent_line_ratio") or 0)
    sm = float(feat.get("sent_len_mean") or 0)
    ss = float(feat.get("sent_len_std") or 0)
    plm = float(feat.get("para_len_mean") or 0)
    dash = float(feat.get("dash_per_1k") or 0)
    punct = float(feat.get("punct_density") or 0)
    pr = float(feat.get("particle_rate") or 0)
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
    else:
        dash_line = f"破折号约 {dash:.1f}/千字；跟样本频率，勿归零也勿翻倍。"

    if ssl >= 0.55 or sspr >= 0.45:
        layout_p0 = (
            "【P0·布局指纹】空行/短段是笔迹本体：意群之间保留空行；"
            "约一半段落可单句成段（短锤/设问/吐槽），另一半 2–4 句说清事实；"
            "禁止合成无空行大段散文墙，也禁止无空行电报码。"
        )
    else:
        layout_p0 = (
            "【P0·布局指纹】段落感跟样本：多句同段推进；"
            "禁止一行一句铺满，也禁止整篇一段墙。"
        )

    if pr >= 0.04:
        voice_p0 = (
            "【P0·口气】口语在场：像跟读者说话；可用轻口语词，勿堆梗合集，勿忽然文言/鲁迅腔。"
        )
    elif pr <= 0.015:
        voice_p0 = (
            "【P0·口气】偏冷书面/旁观；勿忽然网感口语注水，也勿口号宣言连发。"
        )
    else:
        voice_p0 = "【P0·口气】冷热跟样本中段；勿忽然口语注水或忽然文青。"

    rows: list[tuple[str, str]] = [
        ("P0", "【P0·思维】判断必须从动作/场面/反差长出；禁止「升华开头→提纲中段→金句结尾」的通用议论文骨架。"),
        ("P0", "【P0·灵魂】优先遵守 mind.md 的推进步骤（若人格包装有）；rules 只补节奏，不替代怎么想。"),
        ("P0", layout_p0),
        ("P0", voice_p0),
        ("P0", "【P0·反内容】禁止复读 sample 事件/专名/招牌开场（见 content_ban.txt）；新题新事实只听 brief。"),
        ("P0", "【P0·反身份】学笔迹不学身份壳/物种/职业/样本配角；除非 brief 明文角色仿写。"),
        ("P1", f"句长跟样本量级（均约 {sm:.0f}，波动约 {ss:.0f}）；避免句句等长排比。"),
        ("P1", f"段句密度：约 {spp:.1f} 句/段，一段一句占比约 {sspr:.0%}；关键处要有多句推进。"),
        ("P1", f"段体量约 {plm:.0f} 字量级（样本约 {pc} 段/{sc} 句/{chars} 字）；长短听 brief，密度跟样本。"),
        ("P1", "先刺激/场面，再查找或对照，再下判断；收束用短句，不写主题演讲。"),
        ("P1", dash_line),
        ("P1", "每次开篇与核心隐喻允许不同；禁止篇篇复用同一套船/漆/镜/账本万能隐喻（除非 brief 指定）。"),
        ("P2", f"标点疏密约 {punct:.2f} 量级；勿忽然英文腔或整段无标点。"),
        ("P2", "四字格/成语点到为止；别为「有文采」刷屏。"),
        (
            "P2",
            "少用 1.2.3. 清单主结构。"
            if ld < 0.08
            else "可用短列，勿做成 PPT 提纲体。",
        ),
        (
            "P2",
            "禁止「综上所述/赋能/闭环/值得注意的是」等套话。"
            if ai <= 0.5
            else "压低空话，宁冷勿油。",
        ),
        ("P2", "只输出新文正文（除非 brief 要标题）；自检：mind 步骤是否走过 + 空行/口气是否像 + 有无 content_ban 命中。"),
    ]
    return rows


def write_rules_md(path: Path, feat: dict) -> str:
    rows = rules_md_lines(feat)
    body = [
        "# 写作要领 · rules",
        "",
        f"_sensor {VERSION}_",
        "",
        "> **权重**：P0 违反 = 不像本人（灵魂/布局/口气/反串戏）；P1 = 节奏；P2 = 表层。",
        "> **P0 > P1 > P2**。机检绿 ≠ 像；Judge 须按权重打。",
        "",
    ]
    for i, (w, line) in enumerate(rows, 1):
        body.append(f"{i}. ({w}) {line}")
    body.append("")
    # machine-readable weights sidecar hint
    body.append("<!-- weights: P0=1.0 P1=0.55 P2=0.25 -->")
    body.append("")
    text = "\n".join(body)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return text


def score_vs_metrics(feat: dict, anchor: dict) -> float:
    """加权硬分：布局/段句 > 句长 > 助词 > 破折/套话；降低 ttr 等权幻觉。"""
    if "metrics" in anchor and isinstance(anchor["metrics"], dict):
        anchor = {**anchor["metrics"], **{k: v for k, v in anchor.items() if k != "metrics"}}

    def clamp01(x: float) -> float:
        return max(0.0, min(1.0, x))

    weighted: list[tuple[float, float]] = []  # (w, score)

    # P0 layout: single_sent_line_ratio + sents_per_para
    ar = float(anchor.get("single_sent_line_ratio", 0.35) or 0.35)
    fr = float(feat.get("single_sent_line_ratio", ar) or ar)
    if fr <= ar + 0.12:
        layout_s = 1.0
    elif fr <= ar + 0.30:
        layout_s = 0.55
    else:
        layout_s = clamp01(1.0 - (fr - ar) / 0.55)
    weighted.append((1.0, layout_s))

    aspp = float(anchor.get("sents_per_para_mean", 2.0) or 2.0)
    fspp = float(feat.get("sents_per_para_mean", aspp) or aspp)
    if aspp > 0 and 0.55 <= (fspp / aspp) <= 1.7:
        spp_s = 1.0
    else:
        ratio = (fspp / aspp) if aspp else 1.0
        spp_s = clamp01(1.0 - abs(ratio - 1.0))
    weighted.append((1.0, spp_s))

    # P1 sentence length
    sl = clamp01(1.0 - rel_err(feat["sent_len_mean"], anchor.get("sent_len_mean", feat["sent_len_mean"])) / 0.18)
    weighted.append((0.55, sl))
    ss = clamp01(1.0 - rel_err(feat["sent_len_std"], anchor.get("sent_len_std", feat["sent_len_std"] or 1)) / 0.30)
    weighted.append((0.35, ss))

    # P1 particle
    pr = clamp01(1.0 - rel_err(feat["particle_rate"], anchor.get("particle_rate", feat["particle_rate"])) / 0.28)
    weighted.append((0.55, pr))

    # P2 dash / ai / ttr（降权）
    ad = float(anchor.get("dash_per_1k", 0) or 0)
    fd = float(feat.get("dash_per_1k", 0) or 0)
    if ad <= 0.05:
        dash_s = 1.0 if fd <= 0.5 else clamp01(1.0 - (fd - 0.5) / 5.0)
    else:
        ratio = fd / ad if ad else 1.0
        dash_s = 1.0 if 0.5 <= ratio <= 1.5 else clamp01(1.0 - abs(ratio - 1.0))
    weighted.append((0.25, dash_s))

    fp = feat.get("ai_tells_per_1k") or 0
    if fp == 0:
        ai_s = 1.0
    elif fp <= 0.5:
        ai_s = 0.7
    else:
        ai_s = 0.0
    weighted.append((0.35, ai_s))

    ttr_s = clamp01(1.0 - rel_err(feat["ttr"], anchor.get("ttr", feat["ttr"])) / 0.25)
    weighted.append((0.15, ttr_s))

    num = sum(w * s for w, s in weighted)
    den = sum(w for w, _ in weighted) or 1.0
    return round(num / den, 4)


def main() -> int:
    ap = argparse.ArgumentParser(description="magicpen style sensors → rules.md + metrics.json")
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
                "rules_lines": len(rules_text.splitlines()) if rules_text else None,
                "error": feat.get("error"),
            },
            ensure_ascii=False,
        )
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
