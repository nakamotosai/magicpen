<div align="center">

**🌐 Made by [Sai](https://saaaai.com) · [saaaai.com](https://saaaai.com)** — AI workflow · one homepage

**[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)**

</div>

<p align="center">
  <img src="assets/readme/hero.svg" alt="magicpen · 神笔 — installable style pipeline + persona packs" width="100%">
</p>

# magicpen · 神笔 · 神笔

**Installable style pipeline + persona packs.**  
Learn the *handwriting*, not the *identity*. Style ≠ identity. Install once, Write many times; delivery needs `draft` + `RECEIPT`.

| | |
|--|--|
| Chinese brand | **神笔** |
| skill id | **`magicpen`** |
| Japanese | **神笔** |

### Why “magicpen”

The name comes from **Ma Liang and his magic brush** (神笔马良) — with a magic pen, anything you draw becomes real. Applied to writing: **install someone’s style as a persona pack, then write with that pack again and again**. You copy *handwriting and rhythm*, not identity. Gates + a receipt check the draft; it is not “paste into chat and freestyle once.”

This project is an independent open-source tool. “magicpen / 神笔” borrows the meaning of “write anything, and it takes shape”; it involves no story characters, trademarks, or official endorsements.

---

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

Source: [`examples/readme-demo/before-plain.md`](examples/readme-demo/before-plain.md) · [`examples/readme-demo/after-luxun.md`](examples/readme-demo/after-luxun.md) · receipt summary [`examples/readme-demo/RECEIPT.summary.md`](examples/readme-demo/RECEIPT.summary.md)

> Learn the *handwriting*, not the identity shell. Do not pass off a living person’s business tone as “themselves”.

---

## Why not another “paste-and-imitate” chat

| Chat imitator | magicpen |
|---|---|
| Paste source every time | **Install once, Write many** |
| One blob of text | **draft + RECEIPT** |
| Role bleed / structure loss silent | Identity scan + brief gates + default judge |
| No reusable pack | Named persona packs |

---

## Install

```bash
git clone https://github.com/nakamotosai/magicpen
```

The skill directory name must be **`magicpen`**:

| Host | Path |
|------|------|
| omp (primary host) | `~/.omp/agent/skills/magicpen` |
| Claude Code | `~/.claude/skills/magicpen` |
| Codex | `~/.codex/skills/magicpen` |
| This repo only | `.claude/skills/magicpen` |

Persona library (default, **not inside this repo**): `~/.omp/magicpen/personas/<id>/`.

---

## Two facades

User flow: **create a persona** → **write** (pack first, then write).

### Create persona · source → persona pack

```bash
pythonw scripts/run_install.py --raw RAW.md --id mypen --calibrate
```

Outputs: `persona.json` `sample.md` `rules.md` `metrics.json`.

### Write · persona pack + brief → draft + receipt

```bash
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage prepare
# default one-shot draft (OpenAI-compatible chat, see below)
pythonw scripts/run_writer_llm.py --run-dir ~/.omp/magicpen/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage post --run-id rN
pythonw scripts/run_judge_llm.py --run-dir ~/.omp/magicpen/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage finalize --run-id rN
```

**Required deliverables (none optional):** `draft.md` + `RECEIPT.md` + `RECEIPT.json`.  
A receipt is still produced when `deliver_ok=false`.

---

## Local console (manual stepping)

```bash
cd ~/.omp/agent/skills/magicpen/console
pythonw server.py
# http://127.0.0.1:18766/
```

Same `run_install` / `run_write` / injection phrases as the skill.  
W3/W5 use the in-page LLM by default; on a successful receipt at W6, **a copy of the draft is auto-placed on the Desktop** (still kept under `runs/` in the library).

---

## LLM env vars

In-page drafting / scoring / sample search use OpenAI-compatible `chat/completions`:

| Variable | Role |
|----------|------|
| `CLIPROXYAPI_API_KEY` / `MAGICPEN_LLM_KEY` / `OPENAI_API_KEY` | API key (required) |
| `MAGICPEN_LLM_BASE` / `CLIPROXY_BASE` / `OPENAI_BASE_URL` | Base URL (default `http://127.0.0.1:8317`) |
| `MAGICPEN_LLM_MODEL` | Model (default `grok-4.5`) |

Keys are read-only env vars, never written into the repo.

---

## Built-in demos (ready after seed)

The repo ships **three** ready-to-use persona packs under `examples/`. After seeding into the local library, both the console dropdown and `--persona` can address them:

| local id | display | sample | path |
|----------|---------|--------|------|
| `laocai` | 老蔡 | colloquial blank-line fingerprint | `examples/persona-laocai/` |
| `luxun` | 鲁迅 · 藤野先生 (*Mr. Fujino*) | 《藤野先生》(public domain) | `examples/persona-luxun/` |
| `soseki` | 夏目漱石·我是猫肌理 | long-paragraph dry sarcasm | `examples/soseki-wagahai/` |

```bash
# one-shot seed into ~/.omp/magicpen/personas/ (skips if present; --force overwrites samples, keeps runs)
pythonw scripts/seed_demos.py

# write directly with Lu Xun · Mr. Fujino
pythonw scripts/run_write.py --persona luxun --brief BRIEF.md --stage prepare
```

`examples/readme-demo/` holds the before/after artifacts used in this README; it is not a fourth persona.

---

## Contract

Full contract: [SKILL.md](SKILL.md). Orchestration: `references/auto-pipeline.md`.

Self-checks:

```bash
pythonw scripts/assert_magicpen_no_legacy.py
pythonw scripts/assert_public_surface.py
```

---

## Rights

Public material for *style study* is fine.  
Republishing full source as your own work, or impersonating a living person in business, is refused.

---

## License

MIT · [LICENSE](LICENSE)
