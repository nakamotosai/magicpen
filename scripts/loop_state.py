#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""回环状态机：默认 max_loops=5。

状态文件：persona/runs/loop_state.json
命令：init | status | can-write | record | finalize
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_MAX = 5


def state_path(persona: Path) -> Path:
    return persona / "runs" / "loop_state.json"


def load(persona: Path) -> dict:
    p = state_path(persona)
    if not p.exists():
        return {
            "persona": str(persona),
            "max_loops": DEFAULT_MAX,
            "current_loop": 0,
            "status": "idle",
            "history": [],
        }
    return json.loads(p.read_text(encoding="utf-8"))


def save(persona: Path, st: dict) -> None:
    p = state_path(persona)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--persona", type=Path, required=True)
    ap.add_argument(
        "cmd",
        choices=["init", "status", "can-write", "record", "finalize"],
    )
    ap.add_argument("--max-loops", type=int, default=DEFAULT_MAX)
    ap.add_argument("--run-id", type=str, default="")
    ap.add_argument("--hard-score", type=float, default=None)
    ap.add_argument("--judge-pass", type=str, default="")
    ap.add_argument("--gates-ok", type=str, default="")
    ap.add_argument("--reasons", type=str, default="")
    ap.add_argument("--result", type=str, choices=["passed", "exhausted", "aborted"], default="passed")
    args = ap.parse_args()
    persona = args.persona.resolve()

    if args.cmd == "init":
        st = {
            "persona": str(persona),
            "max_loops": args.max_loops,
            "current_loop": 0,
            "status": "in_progress",
            "history": [],
            "updated_at": now(),
        }
        save(persona, st)
        print(json.dumps({"ok": True, "state": st}, ensure_ascii=False, indent=2))
        return 0

    st = load(persona)

    if args.cmd == "status":
        print(json.dumps(st, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "can-write":
        cur = int(st.get("current_loop") or 0)
        mx = int(st.get("max_loops") or DEFAULT_MAX)
        status = st.get("status") or "idle"
        allowed = status in ("idle", "in_progress") and cur < mx
        print(
            json.dumps(
                {
                    "ok": allowed,
                    "allowed": allowed,
                    "current_loop": cur,
                    "max_loops": mx,
                    "status": status,
                    "next_loop": cur + 1 if allowed else None,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if allowed else 1

    if args.cmd == "record":
        if st.get("status") == "idle":
            st["status"] = "in_progress"
        cur = int(st.get("current_loop") or 0) + 1
        mx = int(st.get("max_loops") or DEFAULT_MAX)
        if cur > mx:
            st["status"] = "exhausted"
            save(persona, st)
            print(json.dumps({"ok": False, "error": "max_loops exceeded", "state": st}, ensure_ascii=False))
            return 1
        entry = {
            "loop": cur,
            "run_id": args.run_id or f"r{cur}",
            "hard_score": args.hard_score,
            "judge_pass": None
            if args.judge_pass == ""
            else args.judge_pass.lower() in ("1", "true", "yes", "pass"),
            "gates_ok": None
            if args.gates_ok == ""
            else args.gates_ok.lower() in ("1", "true", "yes"),
            "reasons": [r for r in args.reasons.split("|") if r],
            "at": now(),
        }
        st["current_loop"] = cur
        st.setdefault("history", []).append(entry)
        st["updated_at"] = now()
        # 若本轮全过，不自动 finalize——等 finalize 命令
        if cur >= mx and not (
            entry.get("judge_pass") and entry.get("gates_ok") is not False
        ):
            # 仅标记可能耗尽；仍等 finalize
            pass
        save(persona, st)
        print(json.dumps({"ok": True, "entry": entry, "state": st}, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "finalize":
        st["status"] = args.result
        st["updated_at"] = now()
        save(persona, st)
        print(json.dumps({"ok": True, "state": st}, ensure_ascii=False, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
