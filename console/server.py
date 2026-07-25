#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
卡卡西本机控制台 · http://127.0.0.1:18766/
步进操作 Install / Write；编排 skills/kakashi/scripts facade。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

CONSOLE = Path(__file__).resolve().parent
SKILL = CONSOLE.parent
SCRIPTS = SKILL / "scripts"
STATIC = CONSOLE / "static"
RUNS = CONSOLE / "runs"
PERSONA_LIB = Path.home() / ".claude" / "kakashi" / "personas"

HOST = os.environ.get("KAKASHI_CONSOLE_HOST", "127.0.0.1")
PORT = int(os.environ.get("KAKASHI_CONSOLE_PORT", "18766"))

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from persona_lib import resolve_persona, sanitize_id  # type: ignore

# 对用户：创建人格（内部 mode=install / run_install）
INSTALL_STEPS = [
    {"id": "I1", "key": "ingest", "name": "贴范文", "kind": "human"},
    {"id": "I2", "key": "sensors", "name": "抽笔迹指纹", "kind": "script"},
    {"id": "I3", "key": "calibrate", "name": "布局校准", "kind": "human"},
    {"id": "I4", "key": "quality", "name": "人格包体检", "kind": "script"},
    {"id": "I5", "key": "commit", "name": "写入人格库", "kind": "script"},
]
# 对用户：写稿（内部 mode=write / run_write）
WRITE_STEPS = [
    {"id": "W1", "key": "brief", "name": "写要求", "kind": "human"},
    {"id": "W2", "key": "prepare", "name": "组装提示", "kind": "script"},
    {"id": "W3", "key": "writer", "name": "写正文", "kind": "agent"},
    {"id": "W4", "key": "gates", "name": "机器硬闸", "kind": "script"},
    {"id": "W5", "key": "judge", "name": "评分", "kind": "agent"},
    {"id": "W6", "key": "finalize", "name": "回执交付", "kind": "script"},
]

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def han_count(text: str) -> int:
    return len(re.findall(r"[一-鿿]", text))


def extract_json_object(text: str) -> dict | None:
    """从粘贴/模型输出里抠出第一个 JSON 对象；失败返回 None。"""
    t = (text or "").strip()
    if not t:
        return None
    if t.startswith("```"):
        t = re.sub(r"^```[a-zA-Z0-9_-]*\s*\n?", "", t)
        t = re.sub(r"\n?```\s*$", "", t)
        t = t.strip()
    try:
        obj = json.loads(t)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    i, j = t.find("{"), t.rfind("}") + 1
    if i >= 0 and j > i:
        try:
            obj = json.loads(t[i:j])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            return None
    return None


def _score_10(v) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "—"
    n = max(0.0, min(1.0, n))
    # 0~1 → 约 0~10，一位小数
    return f"{round(n * 10, 1):g}"


def judge_view_from_score(obj: dict | None, *, model: str | None = None) -> dict | None:
    """把 JUDGE_SCORE 机器 JSON 翻成给用户看的人话卡。JSON 本身不是给人读的。"""
    if not isinstance(obj, dict) or not obj:
        return None
    passed = bool(obj.get("pass"))
    axis_a = obj.get("axis_a_fidelity", obj.get("axis_a"))
    axis_b = obj.get("axis_b_brief", obj.get("axis_b"))
    identity_ok = bool(obj.get("identity_ok", True))
    fails = obj.get("fail_reasons") if isinstance(obj.get("fail_reasons"), list) else []
    rewrites = (
        obj.get("rewrite_directives") if isinstance(obj.get("rewrite_directives"), list) else []
    )
    one = str(obj.get("one_line") or "").strip()
    if not one:
        one = "整体过关，可以出回执。" if passed else "还没过关，建议按下面改一改再评。"
    return {
        "pass": passed,
        "verdict": "过了" if passed else "没过",
        "headline": one,
        "style_score": _score_10(axis_a),
        "brief_score": _score_10(axis_b),
        "style_label": "像不像这支笔",
        "brief_label": "有没有按你的要求写",
        "identity_ok": identity_ok,
        "identity_text": "身份干净（没串戏搬人设）" if identity_ok else "身份有风险（可能串了样本身份）",
        "fail_reasons": [str(x) for x in fails if str(x).strip()][:8],
        "rewrite_directives": [str(x) for x in rewrites if str(x).strip()][:8],
        "next_hint": (
            "可以点下一步去出回执。"
            if passed
            else "可以按「建议改」改正文后再评一次；也可以先出回执看机器怎么记。"
        ),
        "model": model or obj.get("model"),
        "for_machine": "下面的 JSON 是给回执机器读的成绩单，一般不用看。",
    }


def load_judge_view(st: dict) -> dict | None:
    """从会话 paths / run 目录读 JUDGE_SCORE → 人话卡。"""
    jp = st.get("paths", {}).get("judge_score")
    cand: list[Path] = []
    if jp:
        cand.append(Path(jp))
    rd = st.get("paths", {}).get("run_dir")
    if rd:
        cand.append(Path(rd) / "JUDGE_SCORE.json")
    if st.get("persona_path") and st.get("run_id"):
        cand.append(Path(st["persona_path"]) / "runs" / st["run_id"] / "JUDGE_SCORE.json")
    seen: set[str] = set()
    for p in cand:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if not p.is_file() or p.stat().st_size <= 2:
            continue
        try:
            obj = json.loads(p.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        if not isinstance(obj, dict):
            continue
        model = None
        if isinstance(st.get("judge_llm"), dict):
            model = st["judge_llm"].get("model")
        return judge_view_from_score(obj, model=model)
    return None


def resolve_desktop_dir() -> Path:
    """本机桌面目录（中文「桌面」/ Desktop / OneDrive 桌面）。"""
    up = os.environ.get("USERPROFILE") or str(Path.home())
    candidates = [
        Path(up) / "Desktop",
        Path(up) / "桌面",
        Path.home() / "Desktop",
        Path.home() / "桌面",
    ]
    for key in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
        od = (os.environ.get(key) or "").strip()
        if od:
            candidates.extend([Path(od) / "Desktop", Path(od) / "桌面"])
    for c in candidates:
        try:
            if c.is_dir():
                return c
        except OSError:
            continue
    d = Path(up) / "Desktop"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _safe_filename(name: str) -> str:
    s = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", (name or "").strip())
    s = re.sub(r"\s+", " ", s).strip(" .")
    return (s[:72] if s else "draft")


def copy_draft_to_desktop(st: dict, draft: Path | str | None = None) -> dict:
    """交稿时把正文拷一份到桌面。库内 runs/ 仍保留。"""
    import shutil

    src = Path(draft or (st.get("paths") or {}).get("draft") or "")
    if not src.is_file():
        # 兜底 run_dir/draft.md
        rd = (st.get("paths") or {}).get("run_dir")
        if rd:
            cand = Path(rd) / "draft.md"
            if cand.is_file():
                src = cand
    if not src.is_file():
        raise RuntimeError("没有可交付的正文 draft.md")

    persona_id = (st.get("persona_id") or "persona").replace("demo:", "")
    # 显示名优先
    display = persona_id
    try:
        meta = load_json(Path(st.get("persona_path") or "") / "persona.json", {}) or {}
        if meta.get("display_name"):
            display = str(meta["display_name"])
    except Exception:
        pass
    run_id = st.get("run_id") or "run"
    ts = datetime.now().strftime("%Y%m%d-%H%M")
    fname = _safe_filename(f"卡卡西_{display}_{run_id}_{ts}") + ".md"
    desk = resolve_desktop_dir()
    dest = desk / fname
    # 重名则加序号
    if dest.exists():
        for i in range(2, 50):
            alt = desk / (_safe_filename(f"卡卡西_{display}_{run_id}_{ts}_{i}") + ".md")
            if not alt.exists():
                dest = alt
                break
    shutil.copy2(src, dest)
    info = {
        "ok": True,
        "desktop_dir": str(desk),
        "desktop_path": str(dest),
        "desktop_name": dest.name,
        "source": str(src.resolve()),
    }
    st.setdefault("paths", {})["desktop_draft"] = str(dest)
    st["desktop_delivery"] = info
    return info


def receipt_view_from_data(
    obj: dict | None,
    *,
    receipt_md: str | None = None,
    desktop: dict | None = None,
) -> dict | None:
    """RECEIPT.json → 给人看的交稿结果卡。"""
    if not isinstance(obj, dict) or not obj:
        return None
    ok = bool(obj.get("deliver_ok"))
    han = obj.get("han")
    try:
        han_s = str(int(han)) if han is not None else "—"
    except (TypeError, ValueError):
        han_s = str(han) if han is not None else "—"
    one = str(obj.get("one_line") or "").strip()
    if not one and receipt_md:
        # 取 markdown 引用行
        for line in (receipt_md or "").splitlines():
            t = line.strip()
            if t.startswith(">") and len(t) > 2:
                one = t.lstrip(">").strip()
                break
    if not one:
        one = "稿子可以交了。" if ok else "回执记了失败，先看原因再改。"
    draft = obj.get("draft") or ""
    persona = obj.get("persona") or ""
    desk = desktop if isinstance(desktop, dict) else {}
    desk_path = desk.get("desktop_path")
    desk_name = desk.get("desktop_name")
    if ok:
        if desk_path:
            next_hint = f"正文已放到桌面：{desk_name or Path(desk_path).name}。本轮结束。"
        else:
            next_hint = "正文已在人格包 runs 里；可再点「放到桌面」。"
    else:
        next_hint = "先看失败原因，改 brief/正文后再从硬闸或评分走一遍。"
    return {
        "deliver_ok": ok,
        "verdict": "可以交了" if ok else "还不能算交稿成功",
        "headline": one,
        "han": han_s,
        "identity_ok": bool(obj.get("identity_ok", True)),
        "identity_text": "身份干净" if obj.get("identity_ok", True) else "身份有风险",
        "gates_ok": bool(obj.get("gates_ok", True)),
        "gates_text": "机器硬闸过了" if obj.get("gates_ok", True) else "机器硬闸没过",
        "judge_pass": obj.get("judge_pass"),
        "judge_text": (
            "评分过了"
            if obj.get("judge_pass") is True
            else ("评分没过" if obj.get("judge_pass") is False else "未单独评分")
        ),
        "style_score": _score_10(obj.get("axis_a_fidelity")),
        "brief_score": _score_10(obj.get("axis_b_brief")),
        "draft_path": str(draft) if draft else None,
        "persona_path": str(persona) if persona else None,
        "desktop_path": desk_path,
        "desktop_name": desk_name,
        "desktop_dir": desk.get("desktop_dir"),
        "next_hint": next_hint,
        "for_machine": "RECEIPT.json 是机器验收账本，一般不用读。",
    }


def load_receipt_view(st: dict) -> dict | None:
    """从 paths / run 读 RECEIPT → 人话交稿卡。"""
    cand: list[Path] = []
    rj = st.get("paths", {}).get("receipt_json")
    if rj:
        cand.append(Path(rj))
    rd = st.get("paths", {}).get("run_dir")
    if rd:
        cand.append(Path(rd) / "RECEIPT.json")
    if st.get("persona_path") and st.get("run_id"):
        cand.append(Path(st["persona_path"]) / "runs" / st["run_id"] / "RECEIPT.json")
    seen: set[str] = set()
    for p in cand:
        key = str(p)
        if key in seen:
            continue
        seen.add(key)
        if not p.is_file() or p.stat().st_size <= 2:
            continue
        obj = load_json(p, {}) or {}
        if not isinstance(obj, dict) or not obj:
            continue
        md_text = None
        md = p.with_suffix(".md")
        if not md.is_file() and p.name.endswith(".json"):
            md = p.parent / "RECEIPT.md"
        if md.is_file():
            try:
                md_text = md.read_text(encoding="utf-8", errors="replace")
            except OSError:
                md_text = None
        view = receipt_view_from_data(obj, receipt_md=md_text)
        # 会话里若已拷过桌面，并上人话卡
        if view and isinstance(st.get("desktop_delivery"), dict):
            d = st["desktop_delivery"]
            view["desktop_path"] = d.get("desktop_path") or view.get("desktop_path")
            view["desktop_name"] = d.get("desktop_name") or view.get("desktop_name")
            view["desktop_dir"] = d.get("desktop_dir") or view.get("desktop_dir")
            if view.get("deliver_ok") and view.get("desktop_path"):
                view["next_hint"] = (
                    f"正文已放到桌面：{view.get('desktop_name') or Path(view['desktop_path']).name}。本轮结束。"
                )
        return view
    return None


def jdump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def load_json(path: Path, default=None):
    if not path.is_file():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def session_dir(sid: str) -> Path:
    return RUNS / sid


def state_path(sid: str) -> Path:
    return session_dir(sid) / "state.json"


def default_state(sid: str, mode: str = "write") -> dict:
    steps_def = INSTALL_STEPS if mode == "install" else WRITE_STEPS
    steps = {s["id"]: {"status": "idle", "error": None, "gate_approved_at": None} for s in steps_def}
    steps[steps_def[0]["id"]]["status"] = "idle"
    return {
        "session_id": sid,
        "mode": mode,
        "persona_id": None,
        "persona_path": None,
        # 创建人格槽位：默认全新 id，禁止静默覆盖已有包
        "new_persona_id": None,
        "new_persona_display": None,
        "install_overwrite": False,
        "run_id": None,
        "gates_only": False,
        "writer_backend": "llm",  # llm=cliproxy Grok 一键写；paste=高级粘贴
        "judge_backend": "paste",
        "raw_source": "paste",  # paste | search — 仅标记来源，范文永远只有一份 raw
        "current_step": steps_def[0]["id"],
        "steps": steps,
        "paths": {},
        "receipt_summary": None,
        "last_job_id": None,
        "log": [],
        "updated_at": now_iso(),
    }


def load_state(sid: str) -> dict:
    p = state_path(sid)
    if not p.is_file():
        st = default_state(sid)
        save_json(p, st)
        return st
    return load_json(p, default_state(sid))


def save_state(st: dict) -> None:
    st["updated_at"] = now_iso()
    save_json(state_path(st["session_id"]), st)


def append_log(st: dict, msg: str) -> None:
    st.setdefault("log", []).append({"t": now_iso(), "msg": msg})
    st["log"] = st["log"][-200:]


def list_personas() -> list[dict]:
    out = []
    if PERSONA_LIB.is_dir():
        for d in sorted(PERSONA_LIB.iterdir()):
            if d.is_dir() and (d / "rules.md").exists():
                meta = load_json(d / "persona.json", {}) or {}
                runs = list_persona_runs(d)
                latest = runs[0] if runs else None
                out.append(
                    {
                        "id": d.name,
                        "path": str(d),
                        "display_name": meta.get("display_name") or d.name,
                        "sample_han": meta.get("sample_han"),
                        "run_count": len(runs),
                        "latest_run": latest.get("id") if latest else None,
                        "latest_step": latest.get("resume_step") if latest else None,
                        "latest_brief_preview": latest.get("brief_preview") if latest else None,
                    }
                )
    # examples demos
    for rel in (
        "persona-laocai/persona-laocai",
        "soseki-wagahai/personas/persona-soseki-wagahai",
        "persona-luxun",
    ):
        p = SKILL / "examples" / rel
        if p.is_dir() and (p / "rules.md").exists():
            out.append({"id": f"demo:{p.name}", "path": str(p), "display_name": f"demo/{p.name}", "demo": True})
    return out


def _run_mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _draft_text_for_run(run_dir: Path) -> str:
    """读 run 的正文：draft.md 优先；空则回退 WRITER_LLM.json 的 text 快照 / .bak。"""
    draft_p = run_dir / "draft.md"
    disk = ""
    if draft_p.is_file():
        disk = draft_p.read_text(encoding="utf-8", errors="replace")
        if han_count(disk) >= 50:
            return disk
    meta = load_json(run_dir / "WRITER_LLM.json", {}) or {}
    snap = meta.get("text") or ""
    if isinstance(snap, str) and han_count(snap) >= 50:
        # 路径串误写入 meta 时丢弃
        if ("\\runs\\" in snap or "/runs/" in snap) and han_count(snap) < 120:
            pass
        else:
            return snap
    # 最近 .bak
    baks = sorted(run_dir.glob("draft.md.bak*"), key=lambda p: p.stat().st_mtime, reverse=True)
    for b in baks:
        try:
            bt = b.read_text(encoding="utf-8", errors="replace")
            if han_count(bt) >= 50:
                return bt
        except OSError:
            continue
    return disk


def soft_clear_file(path: Path | str, *, suffix: str = "bak") -> Path | None:
    """清空前改名备份，不硬删。返回备份路径。"""
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    if not raw.strip():
        return None
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    bak = p.with_name(p.name + f".{suffix}.{ts}")
    try:
        bak.write_text(raw, encoding="utf-8")
        p.write_text("", encoding="utf-8")
        return bak
    except OSError:
        return None


def list_persona_runs(persona: Path | str) -> list[dict]:
    """人格包 runs/ 历史，新→旧。"""
    root = Path(persona)
    runs_dir = root / "runs"
    if not runs_dir.is_dir():
        return []
    items: list[dict] = []
    for d in runs_dir.iterdir():
        if not d.is_dir():
            continue
        name = d.name
        if not re.match(r"^r\d+$", name):
            continue
        brief_p = d / "brief.md"
        draft_p = d / "draft.md"
        receipt_p = d / "RECEIPT.md"
        gates_p = d / "GATES.json"
        judge_p = d / "JUDGE_SCORE.json"
        wp_p = d / "WRITE_PROMPT.md"
        brief = brief_p.read_text(encoding="utf-8", errors="replace") if brief_p.is_file() else ""
        draft = _draft_text_for_run(d)
        has_wp = wp_p.is_file()
        has_draft = han_count(draft) >= 50
        has_gates = gates_p.is_file()
        has_judge = judge_p.is_file()
        has_receipt = receipt_p.is_file()
        # 推断恢复到哪一步
        if has_receipt:
            resume_step = "W6"
            status_label = "已出回执"
        elif has_judge or has_gates:
            resume_step = "W5" if has_judge else "W4"
            status_label = "硬闸/评分中"
        elif has_draft:
            resume_step = "W3"
            status_label = "有正文"
        elif has_wp:
            resume_step = "W3"
            status_label = "已组装提示"
        elif brief.strip():
            resume_step = "W2"
            status_label = "有要求"
        else:
            resume_step = "W1"
            status_label = "空 run"
        mtime = max(
            _run_mtime(d),
            _run_mtime(draft_p) if draft_p.is_file() else 0,
            _run_mtime(brief_p) if brief_p.is_file() else 0,
            _run_mtime(receipt_p) if receipt_p.is_file() else 0,
        )
        items.append(
            {
                "id": name,
                "path": str(d),
                "brief_preview": (brief.strip().replace("\n", " ")[:80] if brief.strip() else ""),
                "brief_han": han_count(brief),
                "draft_han": han_count(draft),
                "has_write_prompt": has_wp,
                "has_draft": has_draft,
                "has_gates": has_gates,
                "has_judge": has_judge,
                "has_receipt": has_receipt,
                "resume_step": resume_step,
                "status_label": status_label,
                "mtime": mtime,
                "updated_at": datetime.fromtimestamp(mtime).isoformat(timespec="seconds") if mtime else None,
            }
        )
    items.sort(key=lambda x: (x.get("mtime") or 0, x["id"]), reverse=True)
    return items


def hydrate_write_from_run(
    st: dict,
    *,
    persona_id: str | None = None,
    run_id: str | None = None,
    fresh: bool = False,
) -> dict:
    """把人格包某次 run 的产物灌进当前会话（写稿模式）。

    fresh=True：只绑定人格，不恢复历史（全新写）。
    """
    raw_pid = (persona_id or st.get("persona_id") or "").strip()
    if not raw_pid:
        raise RuntimeError("未指定人格")
    pid = raw_pid.split(":", 1)[-1] if raw_pid.startswith("demo:") else raw_pid
    # 必须按目标 id 解析路径；禁复用旧 persona_path（切人格会串包）
    persona = Path(resolve_persona(pid))
    st["mode"] = "write"
    # 保持用户选的 id（可含 demo: 前缀）
    st["persona_id"] = raw_pid if persona_id else (st.get("persona_id") or pid)
    if persona_id:
        st["persona_id"] = persona_id
    st["persona_path"] = str(persona)
    st.setdefault("paths", {})
    # 换人格时先清掉上一包的 run 路径，避免 draft/brief 仍指旧目录
    for k in list(st.get("paths", {}).keys()):
        if k not in ("persona", "sample", "rules"):
            st["paths"].pop(k, None)
    st["paths"]["persona"] = str(persona)
    st["paths"]["sample"] = str(persona / "sample.md")
    st["paths"]["rules"] = str(persona / "rules.md")

    if fresh:
        # 全新写：清空 run 进度，保留人格
        for k in list(st.get("paths", {}).keys()):
            if k not in ("persona", "sample", "rules"):
                st["paths"].pop(k, None)
        st["run_id"] = None
        st["handoff"] = None
        st["writer_llm"] = None
        st["gates_data"] = None
        st["receipt_summary"] = None
        st["receipt_data"] = None
        steps_def = WRITE_STEPS
        st["steps"] = {s["id"]: {"status": "idle", "error": None, "gate_approved_at": None} for s in steps_def}
        st["current_step"] = "W1"
        # 会话 brief 也清空，避免串包
        b = session_dir(st["session_id"]) / "brief.md"
        if b.is_file():
            b.write_text("", encoding="utf-8")
        append_log(st, f"切换人格 {st['persona_id']} · 全新写")
        return st

    runs = list_persona_runs(persona)
    if not runs:
        # 无历史：空白写稿，但人格已绑
        steps_def = WRITE_STEPS
        st["steps"] = {s["id"]: {"status": "idle", "error": None, "gate_approved_at": None} for s in steps_def}
        st["current_step"] = "W1"
        st["run_id"] = None
        append_log(st, f"切换人格 {st['persona_id']} · 无历史 run")
        return st

    pick = None
    if run_id:
        pick = next((r for r in runs if r["id"] == run_id), None)
        if not pick:
            raise RuntimeError(f"run 不存在: {run_id}")
    else:
        pick = runs[0]
    run_dir = Path(pick["path"])
    rid = pick["id"]
    st["run_id"] = rid
    # 路径灌入
    mapping = {
        "brief": run_dir / "brief.md",
        "write_prompt": run_dir / "WRITE_PROMPT.md",
        "spawn_prompt": run_dir / "SPAWN_PROMPT.md",
        "agent_handoff": run_dir / "AGENT_HANDOFF.json",
        "orchestrate": run_dir / "ORCHESTRATE.json",
        "draft": run_dir / "draft.md",
        "gates": run_dir / "GATES.json",
        "judge_prompt": run_dir / "JUDGE_PROMPT.md",
        "judge_score": run_dir / "JUDGE_SCORE.json",
        "receipt": run_dir / "RECEIPT.md",
        "receipt_json": run_dir / "RECEIPT.json",
        "run_dir": run_dir,
    }
    for k, p in mapping.items():
        if k == "run_dir" or (isinstance(p, Path) and p.exists()):
            st["paths"][k] = str(p)

    # 会话 brief 与 run 同步（W1 编辑框读会话 brief）
    sdir = session_dir(st["session_id"])
    sdir.mkdir(parents=True, exist_ok=True)
    brief_src = run_dir / "brief.md"
    if brief_src.is_file():
        text = brief_src.read_text(encoding="utf-8", errors="replace")
        (sdir / "brief.md").write_text(text, encoding="utf-8")
        st["paths"]["brief"] = str(sdir / "brief.md")
        # 同时保留 run 内 brief 指针供 prepare 复用；run_write 用会话 brief 也行
        st["paths"]["brief_run"] = str(brief_src)

    # draft 空时：从 WRITER_LLM / .bak 回填磁盘，再标步骤
    draft_p = run_dir / "draft.md"
    recovered = _draft_text_for_run(run_dir)
    if han_count(recovered) >= 50:
        cur_disk = draft_p.read_text(encoding="utf-8", errors="replace") if draft_p.is_file() else ""
        if han_count(cur_disk) < 50:
            draft_p.write_text(recovered if recovered.endswith("\n") else recovered + "\n", encoding="utf-8")
        st["paths"]["draft"] = str(draft_p)

    # 步骤状态按产物推断
    steps = {s["id"]: {"status": "idle", "error": None, "gate_approved_at": None} for s in WRITE_STEPS}
    brief_ok = bool((sdir / "brief.md").is_file() and len((sdir / "brief.md").read_text(encoding="utf-8", errors="replace").strip()) >= 8)
    has_wp = (run_dir / "WRITE_PROMPT.md").is_file()
    has_draft = han_count(recovered) >= 50
    has_gates = (run_dir / "GATES.json").is_file()
    has_judge = (run_dir / "JUDGE_SCORE.json").is_file()
    has_receipt = (run_dir / "RECEIPT.md").is_file() or (run_dir / "RECEIPT.json").is_file()

    if brief_ok:
        steps["W1"] = {"status": "done", "error": None, "gate_approved_at": now_iso()}
    if has_wp:
        steps["W1"]["status"] = "done"
        steps["W2"] = {"status": "done", "error": None, "gate_approved_at": now_iso()}
    if has_draft:
        steps["W3"] = {"status": "await_gate", "error": None, "gate_approved_at": None}
        if has_gates or has_judge or has_receipt:
            steps["W3"] = {"status": "done", "error": None, "gate_approved_at": now_iso()}
    if has_gates:
        g = load_json(run_dir / "GATES.json", {}) or {}
        ok = bool(g.get("ok", g.get("gates_ok", True)))
        steps["W4"] = {"status": "done" if ok else "failed", "error": None if ok else "gates failed", "gate_approved_at": now_iso()}
    if has_judge:
        steps["W5"] = {"status": "done", "error": None, "gate_approved_at": now_iso()}
    elif has_gates and st.get("gates_only"):
        steps["W5"] = {"status": "done", "error": None, "gate_approved_at": now_iso()}
    if has_receipt:
        steps["W6"] = {"status": "done", "error": None, "gate_approved_at": now_iso()}
        rec = load_json(run_dir / "RECEIPT.json", {}) or {}
        if rec:
            st["receipt_summary"] = {
                "deliver_ok": rec.get("deliver_ok"),
                "run_id": rid,
            }

    st["steps"] = steps
    # 当前步 = 第一个未 done 的
    cur = "W6"
    for sid in [s["id"] for s in WRITE_STEPS]:
        if steps.get(sid, {}).get("status") not in ("done",):
            cur = sid
            break
    else:
        cur = "W6"
    st["current_step"] = cur
    if has_draft:
        st["handoff"] = {
            "role": "writer",
            "spawn_instruction": f"已恢复历史 run {rid}；可继续改 draft 或往下走。",
            "spawn_prompt": st["paths"].get("spawn_prompt"),
            "write_target": st["paths"].get("draft"),
            "auto_ran": True,
            "resumed": True,
        }
    elif has_wp:
        st["handoff"] = {
            "role": "writer",
            "spawn_instruction": f"已恢复 {rid} 的组装提示；可一键写正文。",
            "spawn_prompt": st["paths"].get("spawn_prompt"),
            "write_target": st["paths"].get("draft"),
            "auto_ran": False,
            "resumed": True,
        }
    else:
        st["handoff"] = None
    st["writer_llm"] = None
    if (run_dir / "WRITER_LLM.json").is_file():
        st["writer_llm"] = load_json(run_dir / "WRITER_LLM.json", {}) or {}
    st["run_history"] = runs[:20]
    append_log(st, f"恢复人格 {st['persona_id']} run={rid} → {cur}（{pick.get('status_label')}）")
    return st


def reset_write_progress(st: dict, *, scope: str = "all", from_step: str | None = None) -> dict:
    """清除写稿进度。scope=all 全清；from_step=从某步起清后续（含该步产物语义上重做）。"""
    if st.get("mode") != "write":
        raise RuntimeError("仅写稿模式可重置进度")
    if scope == "all":
        return hydrate_write_from_run(st, persona_id=st.get("persona_id"), fresh=True)
    step = from_step or st.get("current_step") or "W1"
    order = [s["id"] for s in WRITE_STEPS]
    if step not in order:
        raise RuntimeError(f"未知步骤 {step}")
    i = order.index(step)
    # 清步骤状态
    for sid in order[i:]:
        set_step(st, sid, "idle", None)
    st["current_step"] = step
    # 清对应产物指针
    if step in ("W1",):
        st["run_id"] = None
        for k in (
            "write_prompt", "spawn_prompt", "agent_handoff", "orchestrate",
            "draft", "gates", "judge_prompt", "judge_score", "receipt", "receipt_json", "run_dir",
        ):
            st.get("paths", {}).pop(k, None)
        st["handoff"] = None
        st["writer_llm"] = None
        st["receipt_summary"] = None
        b = session_dir(st["session_id"]) / "brief.md"
        b.write_text("", encoding="utf-8")
        st["paths"]["brief"] = str(b)
    elif step == "W2":
        st["run_id"] = None
        for k in (
            "write_prompt", "spawn_prompt", "agent_handoff", "orchestrate",
            "draft", "gates", "judge_prompt", "judge_score", "receipt", "receipt_json", "run_dir",
        ):
            st.get("paths", {}).pop(k, None)
        st["handoff"] = None
        st["writer_llm"] = None
        st["receipt_summary"] = None
    elif step == "W3":
        # 保留 prepare；正文只软清（改名 .bak），磁盘 run 历史仍可再打开
        draft = st.get("paths", {}).get("draft")
        if draft:
            soft_clear_file(draft)
        for k in ("gates", "judge_prompt", "judge_score", "receipt", "receipt_json"):
            st.get("paths", {}).pop(k, None)
        # writer_llm 保留在磁盘 WRITER_LLM.json；会话态可清
        st["writer_llm"] = None
        st["receipt_summary"] = None
        if st.get("handoff"):
            st["handoff"]["auto_ran"] = False
    elif step == "W4":
        for k in ("gates", "judge_prompt", "judge_score", "receipt", "receipt_json"):
            st.get("paths", {}).pop(k, None)
        st["receipt_summary"] = None
    elif step == "W5":
        for k in ("judge_score", "receipt", "receipt_json"):
            st.get("paths", {}).pop(k, None)
        st["receipt_summary"] = None
    elif step == "W6":
        for k in ("receipt", "receipt_json"):
            st.get("paths", {}).pop(k, None)
        st["receipt_summary"] = None
    append_log(st, f"重置进度 scope={scope} from={step}")
    return st


def allowed_path(path: Path) -> bool:
    try:
        rp = path.resolve()
    except Exception:
        return False
    roots = [
        PERSONA_LIB.resolve() if PERSONA_LIB.exists() else PERSONA_LIB,
        RUNS.resolve(),
        (SKILL / "examples").resolve(),
        SCRIPTS.resolve(),
    ]
    for root in roots:
        try:
            rp.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def open_in_explorer(target: Path) -> dict:
    """打开资源管理器并尽量选中文件。

    注意：
    - 绝不能对 explorer 用 CREATE_NO_WINDOW —— 进程起了窗口不出现。
    - 用 DETACHED_PROCESS 彻底脱钩，避免偶发拖死 HTTP 线程。
    """
    fp = Path(target)
    try:
        fp = fp.resolve()
    except OSError:
        pass
    if not allowed_path(fp):
        raise RuntimeError("路径不在允许范围内")
    if not fp.exists():
        parent = fp.parent
        if parent.is_dir() and allowed_path(parent):
            fp = parent
        else:
            raise RuntimeError(f"路径不存在: {fp}")

    folder = fp if fp.is_dir() else fp.parent
    opened = str(fp)
    method = "none"
    if sys.platform == "win32":
        # 完全脱离当前进程树，避免 pythonw 子进程窗口被吞
        detach = 0
        if hasattr(subprocess, "DETACHED_PROCESS"):
            detach |= subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
        if hasattr(subprocess, "CREATE_NEW_PROCESS_GROUP"):
            detach |= subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        # 0x00000008 = DETACHED_PROCESS 兜底
        if not detach:
            detach = 0x00000008

        def _spawn(args: list[str]) -> None:
            subprocess.Popen(
                args,
                close_fds=True,
                creationflags=detach,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

        try:
            if fp.is_file():
                # /select,路径 须同一参数；路径含空格也由 list 形式安全传递
                _spawn(["explorer.exe", f"/select,{fp}"])
                method = "explorer_select"
            else:
                _spawn(["explorer.exe", str(fp)])
                method = "explorer_dir"
        except Exception as e1:
            try:
                os.startfile(str(folder))  # type: ignore[attr-defined]
                method = f"startfile:{e1}"
                opened = str(folder)
            except Exception as e2:
                try:
                    _spawn(["cmd.exe", "/c", "start", "", str(folder)])
                    method = f"cmd_start:{e1}/{e2}"
                    opened = str(folder)
                except Exception as e3:
                    raise RuntimeError(f"无法打开文件夹: {e1}; {e2}; {e3}") from e3
    else:
        subprocess.Popen(["xdg-open", str(folder)])
        method = "xdg-open"
        opened = str(folder)
    return {"ok": True, "path": str(fp), "opened": opened, "method": method, "folder": str(folder)}


def run_script(args: list[str], timeout: int = 600) -> tuple[int, str, str]:
    cmd = [sys.executable, *args]
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        cwd=str(SCRIPTS),
        creationflags=CREATE_NO_WINDOW,
    )
    return p.returncode, p.stdout or "", p.stderr or ""


def parse_json_out(stdout: str) -> dict:
    try:
        i, j = stdout.find("{"), stdout.rfind("}") + 1
        if i >= 0 and j > i:
            return json.loads(stdout[i:j])
    except json.JSONDecodeError:
        pass
    return {"raw": stdout[-2000:]}


def start_job(kind: str, fn) -> str:
    jid = uuid.uuid4().hex[:12]
    t0 = time.time()
    with JOBS_LOCK:
        JOBS[jid] = {
            "id": jid,
            "kind": kind,
            "status": "running",
            "pct": 5,
            "log": [],
            "result": None,
            "error": None,
            "started": now_iso(),
            "elapsed_sec": 0,
            "hint": "已启动…",
        }

    def heartbeat():
        # 长任务（尤其 Grok）期间 pct 不能一直 5%，否则用户以为死了
        while True:
            with JOBS_LOCK:
                job = JOBS.get(jid)
                if not job or job.get("status") != "running":
                    return
                elapsed = int(time.time() - t0)
                job["elapsed_sec"] = elapsed
                # 5% → 92% 在约 180s 内缓升，永不假 100
                job["pct"] = min(92, 5 + int(elapsed * 0.48))
                if kind in ("sample_search_llm", "writer_llm", "judge_llm"):
                    label = {
                        "sample_search_llm": "Grok 搜范文",
                        "writer_llm": "Grok 写正文",
                        "judge_llm": "Grok 评分",
                    }.get(kind, "Grok")
                    if elapsed < 15:
                        job["hint"] = f"正在接通 cliproxy · {label}…"
                    elif elapsed < 90:
                        job["hint"] = f"{label} 生成中（已 {elapsed}s，常要 1–3 分钟）"
                    else:
                        job["hint"] = f"仍在等 {label}（已 {elapsed}s）"
                else:
                    job["hint"] = f"运行中 {elapsed}s"
            time.sleep(1.0)

    def worker():
        def log(m: str):
            with JOBS_LOCK:
                JOBS[jid]["log"].append(m)
                JOBS[jid]["log"] = JOBS[jid]["log"][-300:]

        try:
            log(f"job {kind} start")
            res = fn(log)
            with JOBS_LOCK:
                JOBS[jid]["status"] = "done"
                JOBS[jid]["pct"] = 100
                JOBS[jid]["result"] = res
                JOBS[jid]["elapsed_sec"] = int(time.time() - t0)
                JOBS[jid]["hint"] = "完成"
            log("job done")
        except Exception as e:
            with JOBS_LOCK:
                JOBS[jid]["status"] = "failed"
                JOBS[jid]["error"] = str(e)
                JOBS[jid]["pct"] = 100
                JOBS[jid]["elapsed_sec"] = int(time.time() - t0)
                JOBS[jid]["hint"] = "失败"
            log(traceback.format_exc())

    threading.Thread(target=heartbeat, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()
    return jid


def step_list(mode: str):
    return INSTALL_STEPS if mode == "install" else WRITE_STEPS


def set_step(st: dict, sid: str, status: str, error: str | None = None):
    st["steps"].setdefault(sid, {})
    st["steps"][sid]["status"] = status
    st["steps"][sid]["error"] = error
    if status == "done":
        st["steps"][sid]["gate_approved_at"] = now_iso()
    elif status in ("idle", "await_gate", "running", "failed"):
        # 重置时清掉过闸时间
        if status != "running":
            st["steps"][sid]["gate_approved_at"] = None


def step_order(mode: str) -> list[str]:
    return [s["id"] for s in step_list(mode)]


def invalidate_after(st: dict, from_step: str, *, reason: str = "") -> list[str]:
    """改了 from_step 的输入后，把后续步骤打回 idle（先后依赖）。

    from_step 自身不强制改状态（由调用方设 await_gate/idle）。
    返回被重置的 step id 列表。
    """
    order = step_order(st.get("mode") or "write")
    if from_step not in order:
        return []
    i = order.index(from_step)
    cleared: list[str] = []
    for sid in order[i + 1 :]:
        prev = (st.get("steps") or {}).get(sid, {}).get("status")
        if prev and prev != "idle":
            set_step(st, sid, "idle", None)
            cleared.append(sid)
    # 写稿：改 brief/draft 后回执作废
    if from_step in ("W1", "W2", "W3", "W4", "W5") or (
        st.get("mode") == "write" and from_step.startswith("W")
    ):
        if from_step in ("W1", "W2", "W3"):
            st["receipt_summary"] = None
            # 改 brief 或更早：run 产物不可复用
            if from_step in ("W1",):
                st["run_id"] = None
                for k in (
                    "write_prompt",
                    "spawn_prompt",
                    "agent_handoff",
                    "draft",
                    "gates",
                    "judge_prompt",
                    "judge_score",
                    "receipt",
                    "receipt_json",
                    "run_dir",
                ):
                    st.get("paths", {}).pop(k, None)
                st["handoff"] = None
                st["gates_data"] = None
                st["receipt_data"] = None
            elif from_step == "W3":
                # 改 draft：作废闸/评分/回执；保留 prepare 的 SPAWN/WRITE 供重跑或高级复制
                for k in (
                    "gates",
                    "judge_prompt",
                    "judge_score",
                    "receipt",
                    "receipt_json",
                ):
                    st.get("paths", {}).pop(k, None)
        elif from_step == "W4":
            for k in ("judge_score", "receipt", "receipt_json"):
                st.get("paths", {}).pop(k, None)
            st["receipt_summary"] = None
        elif from_step == "W5":
            for k in ("receipt", "receipt_json"):
                st.get("paths", {}).pop(k, None)
            st["receipt_summary"] = None
    # 创建人格：改范文后，库写入结果不能当仍有效
    if st.get("mode") == "install" and from_step == "I1":
        for k in ("rules", "sample", "persona"):
            # 保留 persona_id 选择，但后续须重跑 install
            pass
        st["install_stale"] = True
    if cleared:
        msg = f"级联重置 {','.join(cleared)}"
        if reason:
            msg += f"（{reason}）"
        append_log(st, msg)
    return cleared


def approve_step(st: dict, step: str) -> None:
    """人手/粘贴步过闸：校验最低条件 → done → 前进到下一步。"""
    mode = st.get("mode") or "write"
    order = step_order(mode)
    if step not in order:
        raise RuntimeError(f"未知步骤 {step}")

    if step == "I1":
        raw = Path(st.get("paths", {}).get("raw") or (session_dir(st["session_id"]) / "raw.md"))
        if not raw.is_file():
            raise RuntimeError("还没有范文。请先贴文或一键网搜。")
        text = raw.read_text(encoding="utf-8", errors="replace")
        n = han_count(text)
        if n < 50:
            raise RuntimeError(f"范文太短（{n} 汉字），至少先凑到几十上百字再进下一步")
        st["paths"]["raw"] = str(raw)
        st["content_marks"] = st.get("content_marks") or {}
        st["content_marks"]["raw_han"] = n
    elif step == "W1":
        brief = Path(st.get("paths", {}).get("brief") or (session_dir(st["session_id"]) / "brief.md"))
        if not brief.is_file() or len(brief.read_text(encoding="utf-8", errors="replace").strip()) < 8:
            raise RuntimeError("请先写要求（brief）并保存")
    elif step == "W3":
        draft = Path(st.get("paths", {}).get("draft") or "")
        if not draft.is_file() or han_count(draft.read_text(encoding="utf-8", errors="replace")) < 50:
            raise RuntimeError("请先保存 draft 正文")
    elif step == "W5" and not st.get("gates_only"):
        js = Path(st.get("paths", {}).get("judge_score") or "")
        if not js.is_file() or not js.stat().st_size:
            # 尝试从 run_dir 兜底
            rd = st.get("paths", {}).get("run_dir")
            if rd:
                cand = Path(rd) / "JUDGE_SCORE.json"
                if cand.is_file() and cand.stat().st_size:
                    js = cand
                    st.setdefault("paths", {})["judge_score"] = str(cand)
        if not js.is_file() or not js.stat().st_size:
            raise RuntimeError(
                "还没有评分结果。请点「一键评分（Grok）」，或粘贴合法 JSON，或勾「只跑机器硬闸」。"
            )
        try:
            obj = json.loads(js.read_text(encoding="utf-8", errors="replace"))
            if not isinstance(obj, dict):
                raise ValueError("not object")
        except Exception:
            raise RuntimeError("JUDGE_SCORE.json 不是合法 JSON，请重跑一键评分或重贴")

    set_step(st, step, "done")
    i = order.index(step)
    if i + 1 < len(order):
        nxt = order[i + 1]
        st["current_step"] = nxt
        # 下一步若还是 idle，标成「轮到你/待跑」视觉：保持 idle，is_current 会亮
    else:
        st["current_step"] = step
    append_log(st, f"approve {step} → {st.get('current_step')}")


# ── step runners ─────────────────────────────────────────


def prepare_sample_search(st: dict, query: str) -> dict:
    """I1 网搜范文：组装 sample_search SPAWN（与 skill build_agent_handoff 同 SSOT）。"""
    q = (query or "").strip()
    if len(q) < 4:
        raise RuntimeError("请先写清要搜谁的什么作品（至少几个字）")
    sid = st["session_id"]
    sdir = session_dir(sid)
    sdir.mkdir(parents=True, exist_ok=True)
    raw = sdir / "raw.md"
    qfile = sdir / "SAMPLE_SEARCH_QUERY.md"
    qfile.write_text(q + "\n", encoding="utf-8")
    args = [
        str(SCRIPTS / "build_agent_handoff.py"),
        "--role",
        "sample_search",
        "--query-file",
        str(qfile),
        "--out-dir",
        str(sdir),
        "--write",
        str(raw),
        "--session-id",
        sid,
    ]
    code, out, err = run_script(args)
    data = parse_json_out(out)
    if code != 0 and not data.get("ok"):
        raise RuntimeError(data.get("error") or err or "sample_search handoff failed")
    st["paths"]["raw"] = str(raw)
    st["paths"]["sample_query"] = str(qfile)
    st["paths"]["spawn_prompt"] = data.get("spawn_prompt") or str(sdir / "SPAWN_PROMPT.md")
    st["paths"]["agent_handoff"] = data.get("handoff") or str(sdir / "AGENT_HANDOFF.json")
    st["handoff"] = {
        "role": "sample_search",
        "spawn_instruction": "把 SPAWN_PROMPT 整段注入范文搜集分身；分身只写 raw.md（清洗后正文）",
        "spawn_prompt": st["paths"]["spawn_prompt"],
        "agent_handoff": st["paths"]["agent_handoff"],
        "write_target": str(raw),
        "query": q,
    }
    st["sample_search_query"] = q
    append_log(st, "sample_search SPAWN 已就绪")
    save_state(st)
    return data


def clean_session_raw(st: dict) -> dict:
    """对会话 raw.md 跑 clean_sample_text（贴入或分身写完后可点）。"""
    sid = st["session_id"]
    raw = Path(st.get("paths", {}).get("raw") or (session_dir(sid) / "raw.md"))
    if not raw.is_file():
        raise RuntimeError("还没有范文文本可清洗")
    args = [
        str(SCRIPTS / "clean_sample_text.py"),
        "--in",
        str(raw),
        "--out",
        str(raw),
        "--include-text",
    ]
    code, out, err = run_script(args)
    data = parse_json_out(out)
    if code != 0 and not data.get("ok"):
        raise RuntimeError(data.get("error") or err or "clean failed")
    st["paths"]["raw"] = str(raw)
    text = raw.read_text(encoding="utf-8", errors="replace")
    set_step(st, "I1", "await_gate" if han_count(text) >= 50 else "idle")
    st["current_step"] = "I1"
    st["raw_clean_notes"] = data.get("notes") or []
    append_log(st, f"raw 已清洗 han={data.get('han_after')}")
    save_state(st)
    data["text"] = text
    return data


def run_sample_search_llm(st: dict, query: str, log) -> dict:
    """I1 一键：SPAWN + cliproxy Grok 写 raw + 清洗（网页内完成，用户不用复制）。"""
    q = (query or st.get("sample_search_query") or "").strip()
    if len(q) < 4:
        raise RuntimeError("请先写清要搜谁的什么作品（至少几个字）")
    sid = st["session_id"]
    sdir = session_dir(sid)
    sdir.mkdir(parents=True, exist_ok=True)
    raw = sdir / "raw.md"
    qfile = sdir / "SAMPLE_SEARCH_QUERY.md"
    qfile.write_text(q + "\n", encoding="utf-8")
    st["sample_search_query"] = q
    st["paths"]["sample_query"] = str(qfile)
    st["paths"]["raw"] = str(raw)
    set_step(st, "I1", "running")
    save_state(st)
    log("sample_search_llm … " + q[:80])
    args = [
        str(SCRIPTS / "run_sample_search_llm.py"),
        "--query-file",
        str(qfile),
        "--out-dir",
        str(sdir),
        "--write",
        str(raw),
        "--session-id",
        sid,
    ]
    code, out, err = run_script(args)
    log((out or err)[-2000:])
    data = parse_json_out(out)
    if code != 0 or not data.get("ok"):
        set_step(st, "I1", "failed", data.get("error") or err or "llm sample search failed")
        save_state(st)
        raise RuntimeError(data.get("error") or err or "一键网搜失败")
    st["paths"]["raw"] = str(raw)
    st["paths"]["spawn_prompt"] = data.get("spawn_prompt") or str(sdir / "SPAWN_PROMPT.md")
    st["paths"]["agent_handoff"] = str(sdir / "AGENT_HANDOFF.json")
    st["raw_clean_notes"] = data.get("notes") or []
    st["sample_search_llm"] = {
        "model": data.get("model"),
        "han": data.get("han"),
        "base": data.get("llm_base"),
    }
    st["raw_source"] = "search"
    text = raw.read_text(encoding="utf-8", errors="replace") if raw.is_file() else ""
    invalidate_after(st, "I1", reason="一键网搜覆盖了唯一范文")
    set_step(st, "I1", "await_gate" if han_count(text) >= 50 else "idle")
    st["current_step"] = "I1"
    st["handoff"] = {
        "role": "sample_search",
        "spawn_instruction": "已由控制台直连 cliproxy 跑完；下方 raw 可改。高级：仍可复制 SPAWN 外置重跑。",
        "spawn_prompt": st["paths"]["spawn_prompt"],
        "write_target": str(raw),
        "query": q,
        "auto_ran": True,
    }
    append_log(st, f"一键网搜完成 model={data.get('model')} han={data.get('han')}")
    save_state(st)
    data["text"] = text
    return data


def run_writer_llm(st: dict, log) -> dict:
    """W3 一键：cliproxy Grok 按 WRITE_PROMPT 写 draft（用户不用复制给分身）。"""
    if not st.get("run_id") or not st["paths"].get("run_dir"):
        raise RuntimeError("请先跑 W2 组装提示（prepare）")
    run_dir = Path(st["paths"]["run_dir"])
    wp = Path(st["paths"].get("write_prompt") or (run_dir / "WRITE_PROMPT.md"))
    draft = Path(st["paths"].get("draft") or (run_dir / "draft.md"))
    if not wp.is_file():
        raise RuntimeError("WRITE_PROMPT 不存在，先跑 W2")
    set_step(st, "W3", "running")
    save_state(st)
    log("writer_llm … " + str(draft))
    args = [
        str(SCRIPTS / "run_writer_llm.py"),
        "--run-dir",
        str(run_dir),
        "--write-prompt",
        str(wp),
        "--draft",
        str(draft),
    ]
    code, out, err = run_script(args)
    log((out or err)[-2000:])
    data = parse_json_out(out)
    if code != 0 or not data.get("ok"):
        set_step(st, "W3", "failed", data.get("error") or err or "writer llm failed")
        save_state(st)
        raise RuntimeError(data.get("error") or err or "一键写正文失败")
    text = draft.read_text(encoding="utf-8", errors="replace") if draft.is_file() else ""
    st["paths"]["draft"] = str(draft)
    st["writer_llm"] = {
        "model": data.get("model"),
        "han": data.get("han"),
        "base": data.get("llm_base"),
        # 会话态也带预览；磁盘 WRITER_LLM.json 有完整 text 快照
        "text_preview": (text or "")[:200],
    }
    st["writer_backend"] = "llm"
    st["handoff"] = {
        "role": "writer",
        "spawn_instruction": "已由控制台直连 cliproxy·Grok 写完 draft；可改后点下一步。高级仍可复制 SPAWN 外置重跑。",
        "spawn_prompt": st["paths"].get("spawn_prompt"),
        "write_target": str(draft),
        "auto_ran": True,
    }
    invalidate_after(st, "W3", reason="Grok 写了 draft")
    set_step(st, "W3", "await_gate" if han_count(text) >= 50 else "idle")
    st["current_step"] = "W3"
    append_log(st, f"一键写正文完成 model={data.get('model')} han={data.get('han')}")
    save_state(st)
    data["text"] = text
    return data


def run_judge_llm(st: dict, log) -> dict:
    """W5 一键：cliproxy Grok 写 JUDGE_SCORE.json。"""
    if st.get("mode") != "write":
        raise RuntimeError("仅写稿模式")
    if st.get("gates_only"):
        raise RuntimeError("已勾「只跑机器硬闸」，无需再跑评分；直接 finalize")
    if not st.get("run_id") or not st.get("persona_path"):
        raise RuntimeError("无 run / 人格")
    run_dir = Path(
        st.get("paths", {}).get("run_dir")
        or (Path(st["persona_path"]) / "runs" / st["run_id"])
    )
    jp = Path(st.get("paths", {}).get("judge_prompt") or (run_dir / "JUDGE_PROMPT.md"))
    if not jp.is_file():
        # post 可能只写了 SPAWN
        sp = run_dir / "SPAWN_PROMPT.md"
        if sp.is_file():
            jp = sp
        else:
            raise RuntimeError("请先跑 W4 机器硬闸（生成评分合同）")
    score = Path(st.get("paths", {}).get("judge_score") or (run_dir / "JUDGE_SCORE.json"))
    set_step(st, "W5", "running")
    save_state(st)
    log("judge_llm … " + str(score))
    args = [
        str(SCRIPTS / "run_judge_llm.py"),
        "--run-dir",
        str(run_dir),
        "--judge-prompt",
        str(jp),
        "--score",
        str(score),
    ]
    code, out, err = run_script(args)
    log((out or err)[-2000:])
    data = parse_json_out(out)
    if code != 0 or not data.get("ok"):
        set_step(st, "W5", "failed", data.get("error") or err or "judge llm failed")
        save_state(st)
        raise RuntimeError(data.get("error") or err or "一键评分失败")
    st["paths"]["judge_score"] = str(score)
    st["paths"]["judge_prompt"] = str(jp)
    score_obj = data.get("score_obj") if isinstance(data.get("score_obj"), dict) else None
    if score_obj is None:
        try:
            score_obj = json.loads(score.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            score_obj = {
                "pass": data.get("pass"),
                "axis_a_fidelity": data.get("axis_a_fidelity"),
                "axis_b_brief": data.get("axis_b_brief"),
                "one_line": data.get("one_line"),
            }
    view = judge_view_from_score(score_obj, model=data.get("model"))
    st["judge_llm"] = {
        "model": data.get("model"),
        "pass": data.get("pass"),
        "axis_a_fidelity": data.get("axis_a_fidelity"),
        "axis_b_brief": data.get("axis_b_brief"),
        "one_line": data.get("one_line"),
        "base": data.get("llm_base"),
    }
    st["judge_view"] = view
    st["judge_backend"] = "llm"
    st["handoff"] = {
        "role": "judge",
        "spawn_instruction": (
            (view or {}).get("headline")
            or "评分写好了。看人话结论，点下一步出回执。"
        ),
        "spawn_prompt": st["paths"].get("spawn_prompt"),
        "write_target": str(score),
        "auto_ran": True,
    }
    set_step(st, "W5", "await_gate")
    st["current_step"] = "W5"
    append_log(
        st,
        f"一键评分完成 model={data.get('model')} pass={data.get('pass')} "
        f"a={data.get('axis_a_fidelity')} b={data.get('axis_b_brief')}",
    )
    save_state(st)
    # 附带 score 文本给前端框
    try:
        data["text"] = score.read_text(encoding="utf-8", errors="replace")
    except OSError:
        data["text"] = json.dumps(data.get("score_obj") or {}, ensure_ascii=False, indent=2)
    return data


def resolve_install_slot(st: dict) -> tuple[str, Path]:
    """创建人格槽位策略：

    - 默认全新槽：只用 new_persona_id（或自动 p{sid 尾}），**绝不**静默复用顶栏 persona_id。
    - 覆盖已有：须 install_overwrite=True，且明确给出要覆盖的 id（persona_id 或 new_persona_id）。
    - 目标目录已有 persona.json 且未勾覆盖 → 硬拒。
    """
    sid = st["session_id"]
    overwrite = bool(st.get("install_overwrite"))
    new_id = (st.get("new_persona_id") or "").strip()
    existing = (st.get("persona_id") or "").strip()
    # 去掉 demo: 前缀
    if existing.startswith("demo:"):
        existing = existing.split(":", 1)[-1]

    if overwrite:
        target = sanitize_id(existing or new_id or "")
        if not target:
            raise RuntimeError("勾了覆盖已有，但没选要覆盖的人格 id")
    else:
        # 全新槽：忽略顶栏已选人格，只用新 id / 自动 id
        target = sanitize_id(new_id or f"p{sid[-6:]}")
        # 防呆：若用户填的新 id 撞上库内已有包，要求改名或显式覆盖
        dest = PERSONA_LIB / target
        if dest.is_dir() and (dest / "persona.json").is_file():
            raise RuntimeError(
                f"人格槽位「{target}」已存在。请换新 id，或勾选「覆盖已有人格」并明确选择该槽位。"
            )
        return target, dest

    dest = PERSONA_LIB / target
    if dest.is_dir() and (dest / "persona.json").is_file() and not overwrite:
        raise RuntimeError(
            f"人格槽位「{target}」已存在。请换新 id，或勾选「覆盖已有人格」。"
        )
    return target, dest


def run_install_full(st: dict, log, calibrate: bool = False) -> dict:
    sid = st["session_id"]
    raw = session_dir(sid) / "raw.md"
    if not raw.is_file() or han_count(raw.read_text(encoding="utf-8")) < 50:
        raise RuntimeError("请先在 I1 粘贴/保存足够长的原文")
    pid, persona_dest = resolve_install_slot(st)
    st["persona_id"] = pid
    st["new_persona_id"] = pid
    display = (st.get("new_persona_display") or "").strip()
    args = [
        str(SCRIPTS / "run_install.py"),
        "--raw",
        str(raw),
        "--id",
        pid,
    ]
    if display:
        args.extend(["--display-name", display])
    if calibrate:
        args.append("--calibrate")
    log(
        "run_install "
        + pid
        + (" overwrite" if st.get("install_overwrite") else " new-slot")
        + (f" display={display}" if display else "")
    )
    code, out, err = run_script(args)
    log(out[-1500:] if out else err[-800:])
    data = parse_json_out(out)
    if code != 0 and not data.get("ok"):
        raise RuntimeError(data.get("error") or err or "install failed")
    persona = Path(data.get("persona") or persona_dest)
    st["persona_path"] = str(persona)
    st["paths"]["persona"] = str(persona)
    st["paths"]["sample"] = str(persona / "sample.md")
    st["paths"]["rules"] = str(persona / "rules.md")
    for s in ("I1", "I2", "I3", "I4", "I5"):
        set_step(st, s, "done")
    st["current_step"] = "I5"
    append_log(st, f"创建人格完成 {pid}" + ("（覆盖）" if st.get("install_overwrite") else "（新槽）"))
    save_state(st)
    return data


def run_write_prepare(st: dict, log) -> dict:
    if not st.get("persona_id") and not st.get("persona_path"):
        raise RuntimeError("请先选择人格包")
    brief = session_dir(st["session_id"]) / "brief.md"
    if not brief.is_file():
        raise RuntimeError("请先保存 brief（W1）")
    persona_spec = st.get("persona_path") or st["persona_id"]
    args = [
        str(SCRIPTS / "run_write.py"),
        "--persona",
        str(persona_spec),
        "--brief",
        str(brief),
        "--stage",
        "prepare",
    ]
    log("prepare…")
    code, out, err = run_script(args)
    log((out or err)[-1500:])
    data = parse_json_out(out)
    if not data.get("ok") and code != 0:
        raise RuntimeError(data.get("error") or "prepare failed")
    st["run_id"] = data.get("run_id")
    st["persona_path"] = data.get("persona") or st.get("persona_path")
    run_dir = Path(data["run_dir"]) if data.get("run_dir") else None
    st["paths"].update(
        {
            "brief": str(run_dir / "brief.md") if run_dir else str(brief),
            "write_prompt": data.get("write_prompt"),
            "draft": data.get("draft_target"),
            "run_dir": data.get("run_dir"),
            "spawn_prompt": data.get("spawn_prompt")
            or (str(run_dir / "SPAWN_PROMPT.md") if run_dir else None),
            "agent_handoff": data.get("agent_handoff")
            or (str(run_dir / "AGENT_HANDOFF.json") if run_dir else None),
            "orchestrate": str(run_dir / "ORCHESTRATE.json") if run_dir else None,
        }
    )
    st["handoff"] = {
        "role": "writer",
        "spawn_instruction": "下一键：控制台「一键写正文（Grok）」；高级才复制 SPAWN 外置。",
        "spawn_prompt": st["paths"].get("spawn_prompt"),
        "agent_handoff": st["paths"].get("agent_handoff"),
        "write_target": st["paths"].get("draft"),
        "read": st["paths"].get("write_prompt"),
        "auto_ran": False,
    }
    set_step(st, "W1", "done")
    set_step(st, "W2", "done")
    set_step(st, "W3", "idle")
    st["current_step"] = "W3"
    append_log(st, f"prepare {st['run_id']} handoff=writer → 待一键写正文")
    save_state(st)
    return data


def run_write_post(st: dict, log) -> dict:
    if not st.get("run_id"):
        raise RuntimeError("无 run_id，先 prepare")
    draft = Path(st["paths"].get("draft") or "")
    if not draft.is_file() or han_count(draft.read_text(encoding="utf-8")) < 100:
        raise RuntimeError("draft 不存在或过短；请在 W3 粘贴/写入正文")
    brief = session_dir(st["session_id"]) / "brief.md"
    persona_spec = st.get("persona_path") or st["persona_id"]
    args = [
        str(SCRIPTS / "run_write.py"),
        "--persona",
        str(persona_spec),
        "--brief",
        str(brief),
        "--stage",
        "post",
        "--run-id",
        st["run_id"],
    ]
    if st.get("gates_only"):
        args.append("--gates-only")
    log("post gates…")
    code, out, err = run_script(args)
    log((out or err)[-2000:])
    data = parse_json_out(out)
    run_dir = Path(st["paths"].get("run_dir") or (Path(st["persona_path"]) / "runs" / st["run_id"]))
    st["paths"]["gates"] = str(run_dir / "GATES.json")
    st["paths"]["judge_prompt"] = data.get("judge_prompt") or str(run_dir / "JUDGE_PROMPT.md")
    st["paths"]["judge_score"] = data.get("judge_score") or str(run_dir / "JUDGE_SCORE.json")
    st["paths"]["spawn_prompt"] = data.get("spawn_prompt") or str(run_dir / "SPAWN_PROMPT.md")
    st["paths"]["agent_handoff"] = data.get("agent_handoff") or str(run_dir / "AGENT_HANDOFF.json")
    st["paths"]["orchestrate"] = str(run_dir / "ORCHESTRATE.json")
    set_step(st, "W3", "done")
    set_step(
        st,
        "W4",
        "done" if data.get("gates_ok", data.get("ok")) else "failed",
        None if data.get("gates_ok", True) else "gates failed",
    )
    if st.get("gates_only"):
        set_step(st, "W5", "done")
        st["current_step"] = "W6"
        set_step(st, "W6", "idle")
        st["handoff"] = {
            "role": "gates_only",
            "spawn_instruction": "gates-only：跳过 Judge 分身，合成 JUDGE_SCORE 后可 finalize",
            "spawn_prompt": None,
            "write_target": st["paths"].get("judge_score"),
        }
    else:
        set_step(st, "W5", "await_gate")
        st["current_step"] = "W5"
        st["handoff"] = {
            "role": "judge",
            "spawn_instruction": data.get("spawn_instruction")
            or "读 SPAWN_PROMPT.md 整段注入 Judge 分身；只写 JUDGE_SCORE.json",
            "spawn_prompt": st["paths"].get("spawn_prompt"),
            "agent_handoff": st["paths"].get("agent_handoff"),
            "write_target": st["paths"].get("judge_score"),
            "read": st["paths"].get("judge_prompt"),
        }
    append_log(st, f"post gates_ok={data.get('gates_ok')} handoff={st.get('handoff', {}).get('role')}")
    save_state(st)
    return data


def run_write_finalize(st: dict, log) -> dict:
    if not st.get("run_id"):
        raise RuntimeError("无 run_id")
    if not st.get("gates_only"):
        js = Path(st["paths"].get("judge_score") or "")
        if not js.is_file():
            raise RuntimeError("缺少 JUDGE_SCORE.json；请粘贴评分或改用 gates-only")
    brief = session_dir(st["session_id"]) / "brief.md"
    persona_spec = st.get("persona_path") or st["persona_id"]
    args = [
        str(SCRIPTS / "run_write.py"),
        "--persona",
        str(persona_spec),
        "--brief",
        str(brief),
        "--stage",
        "finalize",
        "--run-id",
        st["run_id"],
    ]
    if st.get("gates_only"):
        args.append("--gates-only")
    log("finalize…")
    code, out, err = run_script(args)
    log((out or err)[-2000:])
    data = parse_json_out(out)
    run_dir = Path(st["paths"].get("run_dir") or "")
    st["paths"]["receipt"] = data.get("receipt_md") or str(run_dir / "RECEIPT.md")
    st["paths"]["receipt_json"] = data.get("receipt_json") or str(run_dir / "RECEIPT.json")
    st["paths"]["draft"] = data.get("draft") or st["paths"].get("draft")
    st["receipt_summary"] = {
        "deliver_ok": data.get("deliver_ok"),
        "receipt": data.get("receipt_md"),
    }
    # 人话交稿卡
    rec_obj = data if isinstance(data, dict) else {}
    # run_write finalize 可能只回路径，补读磁盘
    rj = Path(st["paths"].get("receipt_json") or "")
    if rj.is_file():
        disk = load_json(rj, {}) or {}
        if isinstance(disk, dict) and disk:
            rec_obj = {**disk, **{k: v for k, v in rec_obj.items() if v is not None}}
    md_text = None
    rm = Path(st["paths"].get("receipt") or "")
    if rm.is_file():
        try:
            md_text = rm.read_text(encoding="utf-8", errors="replace")
        except OSError:
            md_text = None
    # 交稿成功 → 自动放一份到桌面（不再要求用户「打开文件夹」）
    desk_info = None
    if data.get("deliver_ok"):
        try:
            desk_info = copy_draft_to_desktop(st, st["paths"].get("draft"))
            log(f"desktop ← {desk_info.get('desktop_path')}")
            append_log(st, f"已放到桌面 {desk_info.get('desktop_name')}")
        except Exception as e:
            log(f"desktop copy failed: {e}")
            append_log(st, f"放到桌面失败: {e}")
            desk_info = {"ok": False, "error": str(e)}
    st["receipt_view"] = receipt_view_from_data(
        rec_obj, receipt_md=md_text, desktop=desk_info if (desk_info or {}).get("ok") else st.get("desktop_delivery")
    )
    if desk_info and desk_info.get("ok") and st.get("receipt_view"):
        data["desktop_path"] = desk_info.get("desktop_path")
        data["desktop_name"] = desk_info.get("desktop_name")
    set_step(st, "W5", "done")
    set_step(st, "W6", "done" if data.get("deliver_ok") else "failed", None if data.get("deliver_ok") else "deliver_ok=false")
    st["current_step"] = "W6"
    append_log(st, f"finalize deliver_ok={data.get('deliver_ok')}")
    save_state(st)
    return data


def enrich_state(st: dict) -> dict:
    """Attach pipeline map + file previews meta for UI."""
    mode = st.get("mode") or "write"
    steps = step_list(mode)
    cur = st.get("current_step")
    pipeline = []
    for s in steps:
        info = st.get("steps", {}).get(s["id"], {})
        pipeline.append(
            {
                **s,
                "status": info.get("status") or "idle",
                "error": info.get("error"),
                "is_current": s["id"] == cur,
            }
        )
    out = dict(st)
    out["pipeline"] = pipeline
    out["pipeline_label"] = "创建人格" if mode == "install" else "写稿"
    # 评分/回执人话卡：JSON 是机器读的，UI 优先看这个
    if mode == "write":
        jv = load_judge_view(st)
        if jv:
            out["judge_view"] = jv
            # 补 judge_llm 摘要，便于旧前端字段
            if not out.get("judge_llm"):
                out["judge_llm"] = {
                    "pass": jv.get("pass"),
                    "one_line": jv.get("headline"),
                    "model": jv.get("model"),
                }
        rv = load_receipt_view(st)
        if rv:
            out["receipt_view"] = rv
            if not out.get("receipt_summary"):
                out["receipt_summary"] = {
                    "deliver_ok": rv.get("deliver_ok"),
                    "receipt": st.get("paths", {}).get("receipt"),
                }
    # 写稿：附带该人格 run 历史（供 UI 切换）
    if mode == "write" and st.get("persona_path"):
        try:
            out["run_history"] = list_persona_runs(st["persona_path"])[:20]
        except Exception:
            out["run_history"] = st.get("run_history") or []
    # file stats
    for key in (
        "draft",
        "brief",
        "raw",
        "write_prompt",
        "spawn_prompt",
        "judge_prompt",
        "receipt",
        "gates",
        "rules",
        "sample",
        "agent_handoff",
        "sample_query",
    ):
        p = st.get("paths", {}).get(key)
        if p and Path(p).is_file():
            t = Path(p).read_text(encoding="utf-8", errors="replace")
            out.setdefault("file_stats", {})[key] = {
                "path": p,
                "han": han_count(t),
                "bytes": len(t.encode("utf-8")),
            }
    # I1 会话 raw 可能尚未进 paths
    if "raw" not in out.get("file_stats", {}):
        cand = session_dir(st["session_id"]) / "raw.md"
        if cand.is_file():
            t = cand.read_text(encoding="utf-8", errors="replace")
            out.setdefault("paths", {})["raw"] = str(cand)
            out.setdefault("file_stats", {})["raw"] = {
                "path": str(cand),
                "han": han_count(t),
                "bytes": len(t.encode("utf-8")),
            }
    if st.get("paths", {}).get("gates") and Path(st["paths"]["gates"]).is_file():
        out["gates_data"] = load_json(Path(st["paths"]["gates"]), {})
    if st.get("paths", {}).get("agent_handoff") and Path(st["paths"]["agent_handoff"]).is_file():
        out["handoff_data"] = load_json(Path(st["paths"]["agent_handoff"]), {})
    if st.get("paths", {}).get("spawn_prompt") and Path(st["paths"]["spawn_prompt"]).is_file():
        # full spawn for agent inject (cap large)
        sp = Path(st["paths"]["spawn_prompt"]).read_text(encoding="utf-8", errors="replace")
        out["spawn_prompt_text"] = sp[:120000]
        out["spawn_prompt_truncated"] = len(sp) > 120000
    if st.get("paths", {}).get("receipt_json") and Path(st["paths"]["receipt_json"]).is_file():
        out["receipt_data"] = load_json(Path(st["paths"]["receipt_json"]), {})
    elif st.get("paths", {}).get("receipt") and Path(st["paths"]["receipt"]).is_file():
        out["receipt_text"] = Path(st["paths"]["receipt"]).read_text(encoding="utf-8", errors="replace")[:4000]
    return out


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(STATIC), **k)

    def log_message(self, fmt, *args):
        # pythonw 下 sys.stderr 可能为 None，写日志不能炸请求
        try:
            err = sys.stderr
            if err is not None:
                err.write("[kakashi-console] " + (fmt % args) + "\n")
        except Exception:
            pass

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, obj):
        self._send(code, jdump(obj))

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def end_headers(self):
        # 静态 HTML/JS/CSS 也禁缓存，避免改 UI 后浏览器仍旧壳
        try:
            p = urlparse(self.path).path
        except Exception:
            p = ""
        if p.endswith((".html", ".js", ".css", "/")) or p in ("", "/"):
            self.send_header("Cache-Control", "no-store, max-age=0")
            self.send_header("Pragma", "no-cache")
        super().end_headers()

    def do_GET(self):
        u = urlparse(self.path)
        path = u.path
        qs = parse_qs(u.query)

        if path == "/api/health":
            return self._json(
                200,
                {
                    "ok": True,
                    "product": "kakashi-console",
                    "version": "0.1",
                    "skill": str(SKILL),
                    "persona_lib": str(PERSONA_LIB),
                },
            )
        if path == "/api/personas":
            return self._json(200, {"personas": list_personas()})
        if path == "/api/sessions":
            RUNS.mkdir(parents=True, exist_ok=True)
            ids = sorted([p.name for p in RUNS.iterdir() if p.is_dir()], reverse=True)
            return self._json(200, {"sessions": ids[:50]})
        if path.startswith("/api/session/"):
            parts = path.strip("/").split("/")
            # /api/session/{id}
            if len(parts) == 3:
                sid = parts[2]
                st = load_state(sid)
                return self._json(200, enrich_state(st))
            # /api/session/{id}/file?path=
            if len(parts) == 4 and parts[3] == "file":
                sid = parts[2]
                rel = (qs.get("path") or [""])[0]
                key = (qs.get("key") or [""])[0]
                st = load_state(sid)
                fp = None
                if key and st.get("paths", {}).get(key):
                    fp = Path(st["paths"][key])
                elif key in ("raw", "brief", "sample_query"):
                    name = "SAMPLE_SEARCH_QUERY.md" if key == "sample_query" else f"{key}.md"
                    cand = session_dir(sid) / name
                    if cand.is_file():
                        fp = cand
                elif key == "spawn_prompt":
                    # 写稿 run 内或 I1 会话目录
                    if st.get("paths", {}).get("spawn_prompt"):
                        fp = Path(st["paths"]["spawn_prompt"])
                    else:
                        cand = session_dir(sid) / "SPAWN_PROMPT.md"
                        if cand.is_file():
                            fp = cand
                elif key == "judge" and st.get("paths", {}).get("judge_score"):
                    fp = Path(st["paths"]["judge_score"])
                elif rel:
                    fp = Path(unquote(rel))
                if not fp or not fp.is_file() or not allowed_path(fp):
                    return self._json(404, {"error": "file not allowed or missing", "key": key})
                text = fp.read_text(encoding="utf-8", errors="replace")
                return self._json(
                    200,
                    {"path": str(fp), "text": text[:200000], "han": han_count(text), "truncated": len(text) > 200000},
                )
        if path.startswith("/api/jobs/"):
            jid = path.rsplit("/", 1)[-1]
            with JOBS_LOCK:
                job = JOBS.get(jid)
            if not job:
                return self._json(404, {"error": "job not found"})
            return self._json(200, job)

        # static
        if path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        u = urlparse(self.path)
        path = u.path
        body = self._read_json()

        if path == "/api/session":
            mode = body.get("mode") or "write"
            if mode not in ("write", "install"):
                mode = "write"
            sid = body.get("session_id") or datetime.now().strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:4]
            st = default_state(sid, mode)
            st["gates_only"] = bool(body.get("gates_only"))
            st["new_persona_id"] = (body.get("new_persona_id") or None) or None
            st["new_persona_display"] = (body.get("new_persona_display") or None) or None
            st["install_overwrite"] = bool(body.get("install_overwrite"))
            # 写稿：可带已有人格，并默认恢复最新 run 历史
            if mode == "write" and body.get("persona_id"):
                try:
                    hydrate_write_from_run(
                        st,
                        persona_id=body["persona_id"],
                        run_id=body.get("run_id"),
                        fresh=bool(body.get("fresh")),
                    )
                except Exception as e:
                    # 人格解析失败时仍建空会话
                    st["persona_id"] = body["persona_id"]
                    append_log(st, f"新建写稿会话，恢复历史失败: {e}")
            elif mode == "install":
                st["persona_id"] = None
                st["persona_path"] = None
                # 仅当用户明文要覆盖时才绑定已有 id
                if st["install_overwrite"] and body.get("persona_id"):
                    st["persona_id"] = body["persona_id"]
                    try:
                        st["persona_path"] = str(resolve_persona(str(body["persona_id"]).replace("demo:", "")))
                    except Exception:
                        pass
            session_dir(sid).mkdir(parents=True, exist_ok=True)
            save_state(st)
            return self._json(200, enrich_state(st))

        if path.startswith("/api/session/") and path.endswith("/sample-search"):
            # 仅组装 SPAWN（高级：外置分身）
            sid = path.split("/")[3]
            st = load_state(sid)
            if st.get("mode") != "install":
                return self._json(400, {"error": "仅「创建人格」模式可用网搜范文"})
            try:
                q = body.get("query") or body.get("text") or ""
                data = prepare_sample_search(st, q)
            except Exception as e:
                return self._json(400, {"error": str(e)})
            return self._json(200, {"ok": True, "handoff": data, "state": enrich_state(load_state(sid))})

        if path.startswith("/api/session/") and path.endswith("/sample-search-run"):
            # 一键：SPAWN + cliproxy Grok 写 raw + 清洗（后台 job）
            parts = path.strip("/").split("/")
            sid = parts[2]
            st = load_state(sid)
            if st.get("mode") != "install":
                return self._json(400, {"error": "仅「创建人格」模式可用一键网搜"})
            q = (body.get("query") or body.get("text") or st.get("sample_search_query") or "").strip()
            if len(q) < 4:
                return self._json(400, {"error": "请先写清要搜谁的什么作品"})
            st["sample_search_query"] = q
            save_state(st)

            def job_fn(log):
                st2 = load_state(sid)
                return run_sample_search_llm(st2, q, log)

            jid = start_job("sample_search_llm", job_fn)
            st = load_state(sid)
            st["last_job_id"] = jid
            set_step(st, "I1", "running")
            save_state(st)
            return self._json(200, {"job_id": jid, "state": enrich_state(load_state(sid))})

        if path.startswith("/api/session/") and path.endswith("/writer-run"):
            # W3 一键：cliproxy Grok 写 draft（后台 job）
            parts = path.strip("/").split("/")
            sid = parts[2]
            st = load_state(sid)
            if st.get("mode") != "write":
                return self._json(400, {"error": "仅「写稿」模式可用一键写正文"})
            if not st.get("run_id") or not (st.get("paths") or {}).get("write_prompt"):
                return self._json(400, {"error": "请先跑 W2 组装提示"})

            def job_fn_writer(log):
                st2 = load_state(sid)
                return run_writer_llm(st2, log)

            jid = start_job("writer_llm", job_fn_writer)
            st = load_state(sid)
            st["last_job_id"] = jid
            set_step(st, "W3", "running")
            save_state(st)
            return self._json(200, {"job_id": jid, "state": enrich_state(load_state(sid))})

        if path.startswith("/api/session/") and path.endswith("/clean-raw"):
            sid = path.split("/")[3]
            st = load_state(sid)
            try:
                data = clean_session_raw(st)
            except Exception as e:
                return self._json(400, {"error": str(e)})
            return self._json(200, {"ok": True, "clean": data, "state": enrich_state(load_state(sid))})

        if path.startswith("/api/session/") and path.endswith("/judge-run"):
            # W5 一键 Grok 评分
            sid = path.split("/")[3]
            st = load_state(sid)
            if st.get("mode") != "write":
                return self._json(400, {"error": "仅「写稿」模式可用一键评分"})
            if st.get("gates_only"):
                return self._json(400, {"error": "已勾「只跑机器硬闸」，无需评分；去 W6 出回执"})
            if not st.get("paths", {}).get("judge_prompt") and not (
                st.get("run_id") and st.get("persona_path")
            ):
                return self._json(400, {"error": "请先跑 W4 机器硬闸"})

            def job_fn_judge(log):
                st2 = load_state(sid)
                return run_judge_llm(st2, log)

            jid = start_job("judge_llm", job_fn_judge)
            st = load_state(sid)
            st["last_job_id"] = jid
            set_step(st, "W5", "running")
            save_state(st)
            return self._json(200, {"job_id": jid, "state": enrich_state(load_state(sid))})

        if path.startswith("/api/session/") and path.endswith("/file"):
            sid = path.split("/")[3]
            st = load_state(sid)
            key = body.get("key") or "brief"
            text = body.get("text") or ""
            sdir = session_dir(sid)
            sdir.mkdir(parents=True, exist_ok=True)
            if key == "raw":
                fp = sdir / "raw.md"
                old = fp.read_text(encoding="utf-8", errors="replace") if fp.is_file() else ""
                fp.write_text(text, encoding="utf-8")
                st["paths"]["raw"] = str(fp)
                # 唯一范文：可选标记来源（贴/搜），不另存第二份
                src = (body.get("raw_source") or st.get("raw_source") or "paste").strip()
                if src not in ("paste", "search"):
                    src = "paste"
                st["raw_source"] = src
                changed = old.strip() != (text or "").strip()
                if changed:
                    invalidate_after(st, "I1", reason="范文已改/覆盖")
                set_step(st, "I1", "await_gate" if han_count(text) >= 50 else "idle")
                st["current_step"] = "I1"
            elif key == "sample_query":
                fp = sdir / "SAMPLE_SEARCH_QUERY.md"
                fp.write_text(text, encoding="utf-8")
                st["paths"]["sample_query"] = str(fp)
                st["sample_search_query"] = text.strip()
            elif key == "brief":
                fp = sdir / "brief.md"
                old = fp.read_text(encoding="utf-8", errors="replace") if fp.is_file() else ""
                # 防前端重绘竞态：空串不得覆盖已有要求
                if not (text or "").strip() and old.strip():
                    return self._json(
                        400,
                        {
                            "error": "拒绝用空内容覆盖已有要求。请重新输入后再保存。",
                            "kept_han": han_count(old),
                            "kept_len": len(old.strip()),
                        },
                    )
                fp.write_text(text, encoding="utf-8")
                st["paths"]["brief"] = str(fp)
                if old.strip() != (text or "").strip():
                    invalidate_after(st, "W1", reason="要求已改")
                set_step(st, "W1", "await_gate" if len(text.strip()) > 10 else "idle")
                st["current_step"] = "W1"
            elif key == "draft":
                # write into persona run draft if prepare done
                draft_p = st.get("paths", {}).get("draft")
                if not draft_p:
                    return self._json(400, {"error": "先跑 prepare 再写 draft"})
                fp = Path(draft_p)
                fp.parent.mkdir(parents=True, exist_ok=True)
                old = fp.read_text(encoding="utf-8", errors="replace") if fp.is_file() else ""
                if not (text or "").strip() and old.strip():
                    return self._json(
                        400,
                        {"error": "拒绝用空内容覆盖已有 draft", "kept_han": han_count(old)},
                    )
                fp.write_text(text, encoding="utf-8")
                if old.strip() != (text or "").strip():
                    invalidate_after(st, "W3", reason="draft 已改")
                set_step(st, "W3", "await_gate" if han_count(text) >= 100 else "idle")
                st["current_step"] = "W3"
            elif key == "judge":
                jp = st.get("paths", {}).get("judge_score")
                if not jp:
                    # default path
                    if not st.get("run_id") or not st.get("persona_path"):
                        return self._json(400, {"error": "无 run"})
                    jp = str(Path(st["persona_path"]) / "runs" / st["run_id"] / "JUDGE_SCORE.json")
                    st["paths"]["judge_score"] = jp
                fp = Path(jp)
                fp.parent.mkdir(parents=True, exist_ok=True)
                old = fp.read_text(encoding="utf-8", errors="replace") if fp.is_file() else ""
                # 空串不得覆盖已有评分
                if not (text or "").strip():
                    if old.strip():
                        return self._json(
                            400,
                            {
                                "error": "评分框是空的，没覆盖已有结果。请点「一键评分」或粘贴 JSON。",
                                "kept": True,
                            },
                        )
                    return self._json(400, {"error": "评分是空的。请点「一键评分（Grok）」或粘贴 JSON。"})
                obj = extract_json_object(text)
                if obj is None:
                    # 磁盘已有合法 JSON：不覆盖，只提示
                    if old.strip():
                        try:
                            json.loads(old)
                            return self._json(
                                400,
                                {
                                    "error": "粘贴内容不是合法 JSON，已保留磁盘上的评分。可改框后重存，或点「一键评分」。",
                                    "kept": True,
                                },
                            )
                        except json.JSONDecodeError:
                            pass
                    return self._json(
                        400,
                        {
                            "error": "Judge 须是 JSON（可从 ```json 围栏里自动抠）。更省事：点「一键评分（Grok）」。"
                        },
                    )
                pretty = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
                fp.write_text(pretty, encoding="utf-8")
                if old.strip() != pretty.strip():
                    invalidate_after(st, "W5", reason="评分已改")
                set_step(st, "W5", "await_gate")
                st["current_step"] = "W5"
            elif key == "rules":
                rp = st.get("paths", {}).get("rules") or (
                    str(Path(st["persona_path"]) / "rules.md") if st.get("persona_path") else None
                )
                if not rp:
                    return self._json(400, {"error": "无 rules 路径"})
                Path(rp).write_text(text, encoding="utf-8")
                st["paths"]["rules"] = rp
            else:
                return self._json(400, {"error": f"unknown key {key}"})
            append_log(st, f"saved {key} han={han_count(text)}")
            save_state(st)
            return self._json(200, enrich_state(st))

        if path.startswith("/api/session/") and path.endswith("/run"):
            # /api/session/{id}/steps/{step}/run
            parts = path.strip("/").split("/")
            if len(parts) != 6:
                return self._json(400, {"error": "bad path"})
            sid, step = parts[2], parts[4]
            st = load_state(sid)
            calibrate = bool(body.get("calibrate"))

            def job_fn(log):
                st2 = load_state(sid)
                if step in ("I2", "I4", "I5", "install_all"):
                    res = run_install_full(st2, log, calibrate=calibrate or step == "I3")
                elif step == "I3":
                    res = run_install_full(st2, log, calibrate=True)
                elif step == "W2":
                    res = run_write_prepare(st2, log)
                elif step == "W4":
                    res = run_write_post(st2, log)
                elif step == "W6":
                    res = run_write_finalize(st2, log)
                else:
                    raise RuntimeError(f"步骤 {step} 请用保存/过闸，不是脚本跑")
                return res

            jid = start_job(step, job_fn)
            st["last_job_id"] = jid
            set_step(st, step if step != "install_all" else "I2", "running")
            save_state(st)
            return self._json(200, {"job_id": jid, "state": enrich_state(load_state(sid))})

        if path.startswith("/api/session/") and path.endswith("/approve"):
            parts = path.strip("/").split("/")
            sid, step = parts[2], parts[4]
            st = load_state(sid)
            try:
                approve_step(st, step)
            except Exception as e:
                return self._json(400, {"error": str(e)})
            save_state(st)
            return self._json(200, enrich_state(st))

        if path.startswith("/api/session/") and path.endswith("/desktop-copy"):
            # 交稿：再放一份正文到桌面（不依赖打开文件夹）
            sid = path.split("/")[3]
            st = load_state(sid)
            if st.get("mode") != "write":
                return self._json(400, {"error": "仅写稿模式可放到桌面"})
            try:
                info = copy_draft_to_desktop(st)
            except Exception as e:
                return self._json(400, {"error": str(e)})
            # 刷新人话卡
            if st.get("receipt_view") or st.get("paths", {}).get("receipt_json"):
                rv = load_receipt_view(st)
                if rv:
                    st["receipt_view"] = rv
            append_log(st, f"再放到桌面 {info.get('desktop_name')}")
            save_state(st)
            return self._json(200, {"ok": True, **info, "state": enrich_state(st)})

        if path.startswith("/api/session/") and path.endswith("/reveal"):
            # 高级：仍可打开库内路径；默认交付流程不再依赖它
            # body 已在 do_POST 开头读过；禁 body or _read_json() —— 空 {} 是假值会再读挂死
            sid = path.split("/")[3] if len(path.strip("/").split("/")) >= 3 else ""
            st = None
            if sid:
                try:
                    st = load_state(sid)
                except Exception:
                    st = None
            p = str((body or {}).get("path") or "").strip()
            # 优先桌面副本，再草稿
            if (not p or p in ("null", "undefined")) and st:
                paths = st.get("paths") or {}
                for k in ("desktop_draft", "draft", "receipt", "run_dir", "persona", "brief"):
                    if paths.get(k):
                        p = paths[k]
                        break
                if not p and st.get("persona_path") and st.get("run_id"):
                    p = str(Path(st["persona_path"]) / "runs" / st["run_id"])
            if not p:
                return self._json(400, {"error": "没有可打开的路径（先出回执或写完正文）"})
            try:
                result = open_in_explorer(Path(p))
            except Exception as e:
                return self._json(400, {"error": str(e)})
            if st is not None:
                append_log(st, f"打开文件夹 {result.get('opened')} ({result.get('method')})")
                save_state(st)
            return self._json(200, result)

        if path.startswith("/api/session/") and path.endswith("/settings"):
            sid = path.split("/")[3]
            st = load_state(sid)
            if "gates_only" in body:
                st["gates_only"] = bool(body["gates_only"])
            if "mode" in body and body["mode"] in ("write", "install"):
                # soft switch: new steps if empty session
                st["mode"] = body["mode"]
                if body["mode"] == "install" and not body.get("install_overwrite"):
                    # 切到创建人格：清空继承人格，避免误写已有槽
                    if "persona_id" not in body:
                        st["persona_id"] = None
                        st["persona_path"] = None
            if "persona_id" in body:
                if not body["persona_id"]:
                    st["persona_id"] = None
                    st["persona_path"] = None
                else:
                    st["persona_id"] = body["persona_id"]
                    for p in list_personas():
                        if p["id"] == body["persona_id"]:
                            st["persona_path"] = p["path"]
                            break
                    else:
                        try:
                            st["persona_path"] = str(resolve_persona(body["persona_id"]))
                        except Exception as e:
                            return self._json(400, {"error": str(e)})
                    # 写稿：默认自动恢复该人格最新 run 历史（除非 fresh=true）
                    if st.get("mode") == "write" and not body.get("fresh"):
                        try:
                            hydrate_write_from_run(
                                st,
                                persona_id=body["persona_id"],
                                run_id=body.get("run_id"),
                                fresh=False,
                            )
                        except Exception as e:
                            return self._json(400, {"error": f"恢复历史失败: {e}"})
                    elif st.get("mode") == "write" and body.get("fresh"):
                        try:
                            hydrate_write_from_run(st, persona_id=body["persona_id"], fresh=True)
                        except Exception as e:
                            return self._json(400, {"error": str(e)})
            if "new_persona_id" in body:
                v = body.get("new_persona_id")
                st["new_persona_id"] = (str(v).strip() if v else None) or None
            if "new_persona_display" in body:
                v = body.get("new_persona_display")
                st["new_persona_display"] = (str(v).strip() if v else None) or None
            if "install_overwrite" in body:
                st["install_overwrite"] = bool(body["install_overwrite"])
            if "writer_backend" in body:
                st["writer_backend"] = body["writer_backend"]
            if "raw_source" in body and body["raw_source"] in ("paste", "search"):
                st["raw_source"] = body["raw_source"]
            if "current_step" in body:
                st["current_step"] = body["current_step"]
            save_state(st)
            return self._json(200, enrich_state(st))

        if path.startswith("/api/session/") and path.endswith("/resume"):
            sid = path.split("/")[3]
            st = load_state(sid)
            if st.get("mode") != "write":
                return self._json(400, {"error": "仅写稿模式可恢复 run"})
            try:
                hydrate_write_from_run(
                    st,
                    persona_id=body.get("persona_id") or st.get("persona_id"),
                    run_id=body.get("run_id"),
                    fresh=bool(body.get("fresh")),
                )
            except Exception as e:
                return self._json(400, {"error": str(e)})
            save_state(st)
            return self._json(200, enrich_state(st))

        if path.startswith("/api/session/") and path.endswith("/reset"):
            sid = path.split("/")[3]
            st = load_state(sid)
            scope = (body.get("scope") or "all").strip()
            try:
                if scope == "all":
                    reset_write_progress(st, scope="all")
                else:
                    reset_write_progress(
                        st,
                        scope="from",
                        from_step=body.get("from_step") or body.get("step") or st.get("current_step"),
                    )
            except Exception as e:
                return self._json(400, {"error": str(e)})
            save_state(st)
            return self._json(200, enrich_state(st))

        return self._json(404, {"error": "not found"})

    def do_PUT(self):
        return self.do_POST()


def _safe_print(msg: str) -> None:
    try:
        if sys.stdout is not None:
            print(msg, flush=True)
    except Exception:
        pass


def main():
    RUNS.mkdir(parents=True, exist_ok=True)
    STATIC.mkdir(parents=True, exist_ok=True)
    httpd = ThreadingHTTPServer((HOST, PORT), Handler)
    _safe_print(f"kakashi console http://{HOST}:{PORT}/")
    _safe_print(f"personas {PERSONA_LIB}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        _safe_print("bye")


if __name__ == "__main__":
    main()
