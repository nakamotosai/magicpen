# kakashi · 卡卡西 · カカシ

**Installable style pipeline + persona packs.**  
Learn the *handwriting*, not the *identity*. Style ≠ identity. Install once, Write many times; delivery needs `draft` + `RECEIPT`.

| | |
|--|--|
| Chinese brand | **卡卡西** |
| skill id | **`kakashi`** |
| Japanese | **カカシ** |

> 中文: [README.md](README.md)

## Why not another “paste-and-imitate” chat

| Chat imitator | kakashi |
|---|---|
| Paste source every time | **Install once, Write many** |
| One blob of text | **draft + RECEIPT** |
| Role bleed / structure loss silent | Identity scan + brief gates + default judge |
| No reusable pack | Named persona packs |

## Install

```bash
git clone https://github.com/nakamotosai/kakashi
```

Skill directory name must be **`kakashi`** under `~/.claude/skills/` (or project `.claude/skills/`).

Persona library (not in this repo): `~/.claude/kakashi/personas/<id>/`.

## Two facades

```bash
pythonw scripts/run_install.py --raw RAW.md --id mypen --calibrate
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage prepare
pythonw scripts/run_writer_llm.py --run-dir ~/.claude/kakashi/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage post --run-id rN
pythonw scripts/run_judge_llm.py --run-dir ~/.claude/kakashi/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage finalize --run-id rN
```

Required deliverables: `draft.md` + `RECEIPT.md` + `RECEIPT.json`.

## Local console

```bash
cd ~/.claude/skills/kakashi/console
pythonw server.py
# http://127.0.0.1:18766/
```

Same facades as the skill. On successful finalize, a copy of the draft is placed on the Desktop.

## LLM env

| Variable | Role |
|----------|------|
| `CLIPROXYAPI_API_KEY` / `KAKASHI_LLM_KEY` / `OPENAI_API_KEY` | API key (required) |
| `KAKASHI_LLM_BASE` / `CLIPROXY_BASE` / `OPENAI_BASE_URL` | Base URL (default `http://127.0.0.1:8317`) |
| `KAKASHI_LLM_MODEL` | Model (default `grok-4.5`) |

## Contract

Full contract: [SKILL.md](SKILL.md).

```bash
pythonw scripts/assert_kakashi_no_legacy.py
pythonw scripts/assert_public_surface.py
```

## Rights

Public material for *style study* is fine.  
Republishing full source as your own work, or impersonating a living person in business, is refused.

## License

MIT · [LICENSE](LICENSE)
