#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""开源面闸：禁把私有主机/用户绝对路径/密钥明文打进 skill 树（相对本脚本）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {
    ".git",
    "__pycache__",
    "archive",
    "holdouts",
    "runs",
    "node_modules",
    ".venv",
    "venv",
}
SKIP_SUFFIX = {".pyc", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".zip"}
# 本脚本自身会提到坏模式作反例，跳过
SELF = Path(__file__).resolve()

BAD_HOST = re.compile(
    r"tail[0-9a-z]+\.ts\.net|vps-jp\.tail|tailscale\.net",
    re.I,
)
BAD_ABS_USER = re.compile(r"[A-Za-z]:\\Users\\[^\\\s\"']+", re.I)
BAD_SECRET = re.compile(
    r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"][^'\"]{12,}"
)
BAD_BEARER = re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]{20,}")


def iter_files():
    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_SUFFIX:
            continue
        if p.resolve() == SELF:
            continue
        # 仅文本类
        if p.suffix.lower() not in {
            "",
            ".md",
            ".py",
            ".js",
            ".html",
            ".css",
            ".json",
            ".txt",
            ".ps1",
            ".yml",
            ".yaml",
            ".toml",
            ".example",
        } and p.name not in {".gitignore", "LICENSE"}:
            # 无后缀可能是脚本；小文件再读
            if p.suffix:
                continue
        yield p


def main() -> int:
    hits: list[str] = []
    for p in iter_files():
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            hits.append(f"READ_FAIL {p.relative_to(ROOT)}: {e}")
            continue
        rel = str(p.relative_to(ROOT)).replace("\\", "/")
        for rx, label in (
            (BAD_HOST, "private_host"),
            (BAD_ABS_USER, "abs_user_path"),
            (BAD_SECRET, "secret_assign"),
            (BAD_BEARER, "bearer_token"),
        ):
            m = rx.search(text)
            if m:
                # 允许文档里写环境变量名，不允许写 tail 主机默认
                if label == "secret_assign" and "os.environ" in text[max(0, m.start() - 80) : m.end() + 40]:
                    continue
                hits.append(f"{label}: {rel}: {m.group(0)[:80]}")
    if hits:
        print("FAIL assert_public_surface")
        for h in hits[:40]:
            print(" ", h)
        if len(hits) > 40:
            print(f"  … +{len(hits) - 40} more")
        return 1
    print("PASS assert_public_surface")
    return 0


if __name__ == "__main__":
    sys.exit(main())
