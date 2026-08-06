# magicpen · 神笔 · 神笔

**Installable style pipeline + persona packs.**  
Learn the *handwriting*, not the *identity*. Style ≠ identity. Install once, Write many times; delivery needs `draft` + `RECEIPT`.

| | |
|--|--|
| Chinese brand | **神笔** |
| skill id | **`magicpen`** |
| Japanese | **神笔** |

> 中文: [README.md](README.md)

### Why “magicpen”

The name comes from **Ma Liang and his magic brush** (神笔马良) — with a magic pen, anything you draw becomes real. Applied to writing: **install someone’s style as a persona pack, then write with that pack again and again**. You copy *handwriting and rhythm*, not identity. Gates + a receipt check the draft; it is not “paste into chat and freestyle once.”

“magicpen / 神笔” is an independent concept, meant to suggest “write anything, and it takes shape”. It involves no story characters, trademarks, or official endorsements.

## Live example · before vs after

Same brief (~200 Chinese characters): **review the magicpen skill itself.**  
**Before** = generic assistant prose (no persona).  
**After** = real run with the **Lu Xun demo persona** from `examples/persona-luxun` (`deliver_ok=true`, 182 han, identity + gates + judge pass; fidelity 0.74 / brief 0.91).

### Before (generic assistant)

> 神笔是一个很有用的 AI 写作技能。你可以把喜欢的文章风格做成人格包，以后写稿时直接调用，不用每次都把原文贴进对话框。它还提供机器检查和回执，方便确认稿子有没有跑偏。适合需要长期保持固定文风的创作者和团队使用。整体流程清晰，安装一次就能反复写，比普通网页仿写更省事，也更可控。

### After (Lu Xun demo persona · real run)

> 开源工具神笔，说是能装文风人格包，再按包写稿，并出验收回执。装一次人格，往后便可反复调用，不必次次从零捏腔调。
>
> 机器闸卡住格式与禁区，回执把过与不过写明白，亦可复核；比起网页上随口仿写，这里多了一道硬验收。
>
> 只会把原文贴进对话框里聊的，往往聊着便跑腔，热闹一阵就散。空口学腔，终究难交差。
>
> 这里却把人格钉成包，写完还有闸与单可查。冷眼看去，热闹的是仿，认真的是验收，后者才算把「像不像」从嘴上搬到纸面上，少些口头空热闹。

Files: [`examples/readme-demo/before-plain.md`](examples/readme-demo/before-plain.md) · [`examples/readme-demo/after-luxun.md`](examples/readme-demo/after-luxun.md) · [`examples/readme-demo/RECEIPT.summary.md`](examples/readme-demo/RECEIPT.summary.md)

Style ≠ identity. Do not impersonate living people for business.

## Why not another “paste-and-imitate” chat

| Chat imitator | magicpen |
|---|---|
| Paste source every time | **Install once, Write many** |
| One blob of text | **draft + RECEIPT** |
| Role bleed / structure loss silent | Identity scan + brief gates + default judge |
| No reusable pack | Named persona packs |

## Install

```bash
git clone https://github.com/nakamotosai/magicpen
```

Skill directory name must be **`magicpen`** under `~/.claude/skills/` (or project `.claude/skills/`).

Persona library (not in this repo): `~/.omp/magicpen/personas/<id>/`.

## Two facades

```bash
pythonw scripts/run_install.py --raw RAW.md --id mypen --calibrate
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage prepare
pythonw scripts/run_writer_llm.py --run-dir ~/.omp/magicpen/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage post --run-id rN
pythonw scripts/run_judge_llm.py --run-dir ~/.omp/magicpen/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage finalize --run-id rN
```

Required deliverables: `draft.md` + `RECEIPT.md` + `RECEIPT.json`.

## Local console

```bash
cd ~/.omp/agent/skills/magicpen/console
pythonw server.py
# http://127.0.0.1:18766/
```

Same facades as the skill. On successful finalize, a copy of the draft is placed on the Desktop.

## LLM env

| Variable | Role |
|----------|------|
| `CLIPROXYAPI_API_KEY` / `MAGICPEN_LLM_KEY` / `OPENAI_API_KEY` | API key (required) |
| `MAGICPEN_LLM_BASE` / `CLIPROXY_BASE` / `OPENAI_BASE_URL` | Base URL (default `http://127.0.0.1:8317`) |
| `MAGICPEN_LLM_MODEL` | Model (default `grok-4.5`) |

## Built-in demos (ready after seed)

Three persona packs ship under `examples/`. Seed into the local lib, then write:

| local id | display | source |
|----------|---------|--------|
| `laocai` | 老蔡 | `examples/persona-laocai/` |
| `luxun` | 鲁迅 · 藤野先生 (*Mr. Fujino*) | `examples/persona-luxun/` |
| `soseki` | 夏目漱石·我是猫肌理 | `examples/soseki-wagahai/` |

```bash
pythonw scripts/seed_demos.py
pythonw scripts/run_write.py --persona luxun --brief BRIEF.md --stage prepare
```

## Contract

Full contract: [SKILL.md](SKILL.md).

```bash
pythonw scripts/assert_magicpen_no_legacy.py
pythonw scripts/assert_public_surface.py
```

## Rights

Public material for *style study* is fine.  
Republishing full source as your own work, or impersonating a living person in business, is refused.

## License

MIT · [LICENSE](LICENSE)
