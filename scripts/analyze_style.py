#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""深度风格分析器：从样本提取 10 维文风指纹 → style_fingerprint.json + 改进版 mind.md。

用法：
  pythonw analyze_style.py --sample sample.md --persona-id luxun --out-dir ~/.omp/magicpen/personas/luxun/

依赖：
  - cliproxy_chat.py（同目录，经 cliproxy 或任意 OpenAI 兼容端点调 LLM）
  - 环境变量 MAGICPEN_LLM_MODEL（指定模型）
  - 环境变量 CLIPROXYAPI_API_KEY（或 MAGICPEN_LLM_KEY / OPENAI_API_KEY）
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from cliproxy_chat import chat_completions  # type: ignore


ANALYSIS_PROMPT = """你是一个文学风格分析专家。你的任务是对一篇范文进行深度风格分析，输出结构化的「风格指纹」(Style Fingerprint)。

分析以下范文，按 10 个维度输出，每个维度包括：
- 该维度的核心特征描述（1-2 句）
- 3-5 条可执行的写作规则（每条带一个来自范文的引证例子）
- 1-2 条「绝对不要做」的警告

## 范文

SAMPLE_PLACEHOLDER

## 10 个分析维度

1. **反讽与讽刺机制 (Irony & Satire)**：作者如何制造反讽？是寓刺于褒、正话反说、还是冷眼旁观？
2. **句式结构与节奏 (Sentence Architecture & Rhythm)**：句子长短分布、复杂句模式、分句之间如何连接、断句节奏。
3. **词汇指纹 (Vocabulary Signature)**：高频词、特色词、文言/白话比例、语气词、副词偏好。
4. **论证与说理方式 (Argumentation Method)**：如何展开论点？用故事/类比/事例/推理？
5. **叙事视角与距离 (Narrative Stance & Distance)**：第一人称如何使用？对读者/对象的距离感？
6. **开头模式 (Opening Patterns)**：如何开篇？场景/论断/疑问/引语？
7. **结尾模式 (Closing Patterns)**：如何收束？总结/冷判/余味/留白？
8. **修辞手法库 (Rhetorical Device Repertoire)**：惯用的修辞手法及其使用方式。
9. **情感表达与克制 (Emotional Expression & Restraint)**：情感如何流露？直接还是含蓄？
10. **时代语感与文体特征 (Period Flavor)**：文言/旧写词、时代特有的表达方式。

## 输出格式

必须是严格的 JSON 格式：

```json
{
  "author": "作者名",
  "style_fingerprint": {
    "irony_and_satire": { "core": "核心特征", "rules": ["规则1（例证）", "规则2"], "donts": ["警告1"] },
    "sentence_architecture": { ... },
    "vocabulary_signature": { ... },
    "argumentation_method": { ... },
    "narrative_stance": { ... },
    "opening_patterns": { ... },
    "closing_patterns": { ... },
    "rhetorical_device_repertoire": { ... },
    "emotional_expression": { ... },
    "period_flavor": { ... }
  },
  "top_3_most_important_rules": ["规则1", "规则2", "规则3"],
  "must_avoid_at_all_costs": ["绝对不要做1", "绝对不要做2"]
}
```

只输出 JSON，不要其他文字。"""


def load_sample_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def gen_mind_from_fingerprint(fp: dict, persona_id: str) -> str:
    """从风格指纹生成改进版 mind.md。"""
    sf = fp.get("style_fingerprint", {})
    lines = []
    lines.append("# 思维链 · mind（persona `" + persona_id + "`）")
    lines.append("")
    lines.append("> 可迁移的「怎么想」。写新题换事实，不换脑回路。禁止把下列步骤写成样本事件复述。")
    lines.append("")

    # 反讽驱动
    irony = sf.get("irony_and_satire", {})
    irony_core = irony.get("core", "反讽驱动写作")
    lines.append("## 核心驱动：" + irony_core)
    lines.append("")
    lines.append("- " + irony_core)
    lines.append("- 反讽是**骨架**不是装饰：整篇文章的推进逻辑靠反讽张力驱动，不是偶尔加一句俏皮话。")
    lines.append("")

    # 叙事身份
    stance = sf.get("narrative_stance", {})
    stance_core = stance.get("core", "第一人称观察者")
    lines.append("## 叙事身份")
    lines.append("")
    lines.append("- " + stance_core)
    lines.append("- 用轻动词（我见了/我查了/我便/我记得），少用我认为/我觉得。")
    lines.append("")

    # 判断步骤
    lines.append("## 判断怎么长出来（按序 · 不可颠倒）")
    lines.append("")
    lines.append("1. **先摆一个具体场景/细节/物件**——不先表态、不先升华、不先讲道理。")
    lines.append("2. **在场景中嵌入矛盾或反差**——让读者自己发现不对。")
    lines.append("3. **用褒词写丑态/用平淡写不公**——寓刺于褒，正话反说。")
    lines.append("4. **借他人之口/动作体现讽刺**——让旁观者或当事人自己现身说法。")
    lines.append("5. **冷峻短句收束**——不解释、不抒情、不升华。一句冷判结束。")
    lines.append("")

    # 句式节奏
    arch = sf.get("sentence_architecture", {})
    arch_core = arch.get("core", "长短句交错")
    lines.append("## 句式节奏指纹")
    lines.append("")
    lines.append("- " + arch_core)
    for r in arch.get("rules", []):
        if len(r) > 5:
            lines.append("- " + r)
    lines.append("")

    # 词汇
    vocab = sf.get("vocabulary_signature", {})
    vocab_core = vocab.get("core", "文白夹杂")
    lines.append("## 词汇指纹")
    lines.append("")
    lines.append("- " + vocab_core)
    for r in vocab.get("rules", [])[:3]:
        if len(r) > 5:
            lines.append("- " + r)
    lines.append("")

    # 论证方式
    arg = sf.get("argumentation_method", {})
    arg_core = arg.get("core", "叙事代说理")
    lines.append("## 论证方式")
    lines.append("")
    lines.append("- " + arg_core)
    lines.append("- 论点藏在故事/细节里，禁止直接说「我认为」「由此可见」。")
    lines.append("")

    # 情感
    emotion = sf.get("emotional_expression", {})
    emo_core = emotion.get("core", "情感高度克制")
    lines.append("## 情感表达")
    lines.append("")
    lines.append("- " + emo_core)
    lines.append("- 情感通过细节和动作间接流露，禁止直接抒情或呼喊。")
    lines.append("")

    # 绝对不做
    lines.append("## 绝对不做")
    lines.append("")
    avoid = fp.get("must_avoid_at_all_costs", [])
    for i, a in enumerate(avoid, 1):
        lines.append(str(i) + ". " + a)
    lines.append("6. 不把样本事件当新文开场（见 content_ban）。")
    lines.append("7. 不在结尾升华主题——冷峻收束即可。")
    lines.append("")

    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="magicpen 深度风格分析器")
    ap.add_argument("--sample", type=Path, required=True, help="样本文本路径")
    ap.add_argument("--persona-id", type=str, required=True, help="人格 ID")
    ap.add_argument("--out-dir", type=Path, required=True, help="输出目录（人格包目录）")
    args = ap.parse_args()

    sample = load_sample_text(args.sample)
    prompt = ANALYSIS_PROMPT.replace("SAMPLE_PLACEHOLDER", sample)
    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print("分析风格中（调用 LLM）……", file=sys.stderr)

    try:
        resp = chat_completions(
            [
                {"role": "system", "content": "你是一个文学风格分析专家。只输出 JSON。"},
                {"role": "user", "content": prompt},
            ],
            temperature=0.3,
            max_tokens=8192,
            timeout=300,
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": f"LLM 调用失败：{e}"}, ensure_ascii=False))
        return 2

    raw = resp.get("choices", [{}])[0].get("message", {}).get("content", "")
    if not raw:
        print(json.dumps({"ok": False, "error": "LLM 返回空"}, ensure_ascii=False))
        return 3

    # 解析 JSON
    try:
        import re
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if m:
            data = json.loads(m.group())
        else:
            data = json.loads(raw)
    except (json.JSONDecodeError, AttributeError) as e:
        print(json.dumps({"ok": False, "error": f"JSON 解析失败：{e}", "raw": raw[:500]}, ensure_ascii=False))
        return 4

    # 写入 style_fingerprint.json
    fp_path = out_dir / "style_fingerprint.json"
    fp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # 生成 mind.md
    mind = gen_mind_from_fingerprint(data, args.persona_id)
    mind_path = out_dir / "mind.md"
    mind_path.write_text(mind, encoding="utf-8")

    print(
        json.dumps(
            {
                "ok": True,
                "style_fingerprint": str(fp_path),
                "mind": str(mind_path),
                "persona_id": args.persona_id,
                "author": data.get("author", ""),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())