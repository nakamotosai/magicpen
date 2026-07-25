# 卡卡西 · kakashi · カカシ

**可安装的文风产线 + 人格包。**  
学笔迹，不学身份。**风格 ≠ 身份**。Install 一次，Write 多次；交稿要有 `draft` + `RECEIPT`。

| | |
|--|--|
| 中文 | **卡卡西** |
| skill | **`kakashi`** |
| 日文 | **カカシ** |

> English: [README.en.md](README.en.md)

---

## 和网页仿写差在哪

| 网页 AI | 卡卡西 |
|---|---|
| 每次贴原文 | **Install 一次，Write 多次** |
| 只出一篇字 | **draft + RECEIPT 验收回执** |
| 串角色/掉结构常静默 | 身份硬扫 + brief 机检 + 默认评分 |
| 无法点名复用 | 人格包可安装、可点名 |

---

## 装

```bash
git clone https://github.com/nakamotosai/kakashi
```

技能目录名必须是 **`kakashi`**：

| 宿主 | 路径 |
|------|------|
| Claude Code | `~/.claude/skills/kakashi` |
| Codex | `~/.codex/skills/kakashi` |
| 仅本项目 | `.claude/skills/kakashi` |

人格库默认（**不在本仓库内**）：`~/.claude/kakashi/personas/<id>/`。

---

## 两入口

用户话术：**创建人格** → **写稿**（先有包，再写）。

### 创建人格 · 原文 → 人格包

```bash
pythonw scripts/run_install.py --raw RAW.md --id mypen --calibrate
```

产物：`persona.json` `sample.md` `rules.md` `metrics.json`。

### 写稿 · 人格包 + 要求 → 稿 + 回执

```bash
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage prepare
# 默认一键写正文（OpenAI 兼容 chat，见下）
pythonw scripts/run_writer_llm.py --run-dir ~/.claude/kakashi/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage post --run-id rN
pythonw scripts/run_judge_llm.py --run-dir ~/.claude/kakashi/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage finalize --run-id rN
```

**交付物（缺一不可）：** `draft.md` + `RECEIPT.md` + `RECEIPT.json`。  
`deliver_ok=false` 也要出回执。

---

## 本机控制台（人手步进）

```bash
cd ~/.claude/skills/kakashi/console
pythonw server.py
# http://127.0.0.1:18766/
```

与 skill **同一套** `run_install` / `run_write` / 注入词。  
W3/W5 默认页内 LLM；W6 出回执成功时**自动拷一份正文到桌面**（库内 `runs/` 仍保留）。

---

## LLM 环境变量

页内写正文 / 评分 / 范文网搜走 OpenAI 兼容 `chat/completions`：

| 变量 | 含义 |
|------|------|
| `CLIPROXYAPI_API_KEY` 或 `KAKASHI_LLM_KEY` 或 `OPENAI_API_KEY` | 密钥（必填） |
| `KAKASHI_LLM_BASE` 或 `CLIPROXY_BASE` 或 `OPENAI_BASE_URL` | 基址，默认 `http://127.0.0.1:8317` |
| `KAKASHI_LLM_MODEL` | 模型，默认 `grok-4.5` |

密钥只读环境变量，不写进仓库。

---

## Demo

- `examples/persona-laocai`
- `examples/soseki-wagahai`
- `examples/persona-luxun`

---

## 合同全文

见 [SKILL.md](SKILL.md)。编排：`references/auto-pipeline.md`。

自检：

```bash
pythonw scripts/assert_kakashi_no_legacy.py
pythonw scripts/assert_public_surface.py
```

---

## 权利

公开材料学写法 → 可以。  
整篇原文当己作发表 / 冒充在世真人商务 → **拒绝**。

---

## 许可

MIT · [LICENSE](LICENSE)
