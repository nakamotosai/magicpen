#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把仓库 examples 里的三套预设人格包装进本机库。

  pythonw scripts/seed_demos.py
  pythonw scripts/seed_demos.py --force   # 覆盖已存在 id

装完后：
  ~/.omp/magicpen/personas/laocai   老蔡
  ~/.omp/magicpen/personas/luxun    鲁迅 · 藤野先生
  ~/.omp/magicpen/personas/soseki   夏目漱石·我是猫肌理

即可：
  pythonw scripts/run_write.py --persona luxun --brief BRIEF.md --stage prepare
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from persona_lib import DEFAULT_LIB, sanitize_id, utc_now, write_persona_meta

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"

# src 相对 examples/；装到本机 id 固定，便于 README / 控制台
DEMOS: list[dict] = [
    {
        "id": "laocai",
        "display_name": "老蔡",
        "src": EXAMPLES / "persona-laocai" / "persona-laocai",
        "note": "口语空行指纹 demo",
    },
    {
        "id": "luxun",
        "display_name": "鲁迅 · 藤野先生",
        "src": EXAMPLES / "persona-luxun",
        "note": "《藤野先生》公有领域范文；风格≠身份",
    },
    {
        "id": "soseki",
        "display_name": "夏目漱石·我是猫肌理",
        "src": EXAMPLES / "soseki-wagahai" / "personas" / "persona-soseki-wagahai",
        "note": "长段冷嘲 demo；写稿禁猫/苦沙弥等身份壳",
    },
]

COPY_NAMES = (
    "sample.md",
    "rules.md",
    "metrics.json",
    "identity_ban.txt",
    "cut_meta.json",
)


def seed_one(demo: dict, *, force: bool) -> dict:
    pid = sanitize_id(demo["id"])
    src: Path = demo["src"]
    if not src.is_dir() or not (src / "sample.md").is_file():
        return {"id": pid, "ok": False, "error": f"demo source missing: {src}"}
    dest = DEFAULT_LIB / pid
    if dest.exists() and not force:
        # 已有则跳过，不抹用户 runs
        return {
            "id": pid,
            "ok": True,
            "skipped": True,
            "path": str(dest),
            "display_name": demo["display_name"],
            "note": "已存在；--force 可覆盖样本/rules（不删 runs）",
        }
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for name in COPY_NAMES:
        sp = src / name
        if sp.is_file():
            shutil.copy2(sp, dest / name)
            copied.append(name)
    # v3.4 灵魂层（mind.md + content_ban.txt）：examples 源不含，落库后启发式生成（无 LLM 依赖）
    import subprocess

    gen = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "extract_mind_and_bans.py"), "--persona", str(dest)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if gen.returncode == 0:
        for soul in ("mind.md", "content_ban.txt"):
            if (dest / soul).is_file():
                copied.append(soul)
    else:
        copied.append(f"soul_gen_failed: {gen.returncode}")
    # persona.json 用本机 id（examples 里可能是旧 meta）
    sample = (dest / "sample.md").read_text(encoding="utf-8", errors="replace")
    import re

    han = len(re.findall(r"[一-鿿]", sample))
    meta = {
        "id": pid,
        "display_name": demo["display_name"],
        "sample_han": han,
        "demo": True,
        "demo_note": demo.get("note"),
        "source_example": str(src.relative_to(ROOT)).replace("\\", "/"),
        "lib": str(DEFAULT_LIB),
        "created_at": utc_now(),
    }
    # 保留 metrics 里的 layout 若有
    mp = dest / "metrics.json"
    if mp.is_file():
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
            if isinstance(m, dict) and m.get("layout_score") is not None:
                meta["layout_score"] = m.get("layout_score")
        except json.JSONDecodeError:
            pass
    write_persona_meta(dest, meta)
    return {
        "id": pid,
        "ok": True,
        "skipped": False,
        "path": str(dest),
        "display_name": demo["display_name"],
        "copied": copied,
        "sample_han": han,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="seed magicpen demo personas into local lib")
    ap.add_argument("--force", action="store_true", help="覆盖已存在包的样本/rules（保留 runs/）")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    DEFAULT_LIB.mkdir(parents=True, exist_ok=True)
    results = [seed_one(d, force=args.force) for d in DEMOS]
    payload = {
        "ok": all(r.get("ok") for r in results),
        "lib": str(DEFAULT_LIB),
        "results": results,
        "next": "控制台选人格 luxun / laocai / soseki，或 run_write --persona luxun",
    }
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    print(text)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
