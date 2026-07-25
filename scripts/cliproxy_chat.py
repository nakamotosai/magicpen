#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""薄封装：经 cliproxyapi 调 chat/completions（默认 grok-4.5）。

密钥只读环境变量，不落盘、不进日志全文：
  CLIPROXYAPI_API_KEY / OPENAI_API_KEY / KAKASHI_LLM_KEY
  KAKASHI_LLM_BASE / CLIPROXY_BASE / OPENAI_BASE_URL（默认 http://127.0.0.1:8317）
  KAKASHI_LLM_MODEL（默认 grok-4.5）

  pythonw cliproxy_chat.py --prompt SPAWN.md --out raw.md
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

# 公开默认：本机 OpenAI 兼容口；私有网关请用环境变量覆盖
DEFAULT_BASE = "http://127.0.0.1:8317"
DEFAULT_MODEL = "grok-4.5"


def resolve_base() -> str:
    b = (
        os.environ.get("KAKASHI_LLM_BASE")
        or os.environ.get("CLIPROXY_BASE")
        or os.environ.get("OPENAI_BASE_URL")
        or DEFAULT_BASE
    ).strip().rstrip("/")
    # Anthropic base 常无 /v1；chat 要挂 /v1
    if b.endswith("/v1"):
        return b
    return b


def resolve_key() -> str:
    return (
        os.environ.get("KAKASHI_LLM_KEY")
        or os.environ.get("CLIPROXYAPI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or ""
    ).strip()


def chat_completions(
    messages: list[dict],
    *,
    model: str | None = None,
    temperature: float = 0.4,
    max_tokens: int = 8192,
    timeout: int = 300,
) -> dict:
    base = resolve_base()
    key = resolve_key()
    if not key:
        raise RuntimeError(
            "缺少 LLM 密钥：请设环境变量 CLIPROXYAPI_API_KEY（或 KAKASHI_LLM_KEY）"
        )
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    body = {
        "model": model or os.environ.get("KAKASHI_LLM_MODEL") or DEFAULT_MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            code = resp.status
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")[:2000]
        raise RuntimeError(f"LLM HTTP {e.code}: {err_body}") from e
    except Exception as e:
        raise RuntimeError(f"LLM 请求失败: {e}") from e

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"LLM 返回非 JSON（HTTP {code}）: {raw[:500]}") from e

    choice0 = (payload.get("choices") or [{}])[0]
    msg = choice0.get("message") or {}
    text = msg.get("content")
    if isinstance(text, list):
        # 部分网关 content 为块数组
        parts = []
        for block in text:
            if isinstance(block, dict) and block.get("type") in ("text", "output_text"):
                parts.append(block.get("text") or block.get("content") or "")
            elif isinstance(block, str):
                parts.append(block)
        text = "".join(parts)
    if not text:
        # 兼容 reasoning-only / 其它字段
        text = (
            msg.get("reasoning_content")
            or choice0.get("text")
            or msg.get("output_text")
            or ""
        )
    # 偶发 content 为空字符串但 refusal/annotations
    if not str(text).strip() and msg.get("refusal"):
        raise RuntimeError(f"LLM refusal: {msg.get('refusal')}")
    if not str(text).strip():
        raise RuntimeError(
            "LLM 返回空正文（可能池配额耗尽、网关空 200，或几乎全是 reasoning）"
        )
    return {
        "ok": True,
        "model": payload.get("model") or body["model"],
        "text": str(text),
        "usage": payload.get("usage"),
        "base": base,
    }


def strip_fence(text: str) -> str:
    t = (text or "").strip()
    m = re.match(r"^```(?:markdown|md|text)?\s*\n([\s\S]*?)\n```\s*$", t)
    if m:
        return m.group(1).strip() + "\n"
    return t if t.endswith("\n") else t + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description="cliproxy chat thin client")
    ap.add_argument("--prompt", type=Path, help="整段 user/system 提示文件")
    ap.add_argument("--system", type=str, default="你是认真执行任务的助手。只输出任务要求的正文。")
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--model", type=str, default=None)
    ap.add_argument("--max-tokens", type=int, default=8192)
    args = ap.parse_args()
    if not args.prompt or not args.prompt.is_file():
        print(json.dumps({"ok": False, "error": "need --prompt file"}, ensure_ascii=False))
        return 2
    prompt = args.prompt.read_text(encoding="utf-8")
    try:
        res = chat_completions(
            [
                {"role": "system", "content": args.system},
                {"role": "user", "content": prompt},
            ],
            model=args.model,
            max_tokens=args.max_tokens,
        )
    except Exception as e:
        print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        return 1
    text = strip_fence(res["text"])
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(text, encoding="utf-8")
        res["path"] = str(args.out.resolve())
        res["han"] = len(re.findall(r"[一-鿿]", text))
        # 不把全文打进 stdout（可能很长）
        out = {k: v for k, v in res.items() if k != "text"}
        out["ok"] = True
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        res["text"] = text
        print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
