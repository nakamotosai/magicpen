# 卡卡西 · kakashi · カカシ

**可安装的文风产线 + 人格包。**  
学笔迹，不学身份。**风格 ≠ 身份**。Install 一次，Write 多次；交稿要有 `draft` + `RECEIPT`。

| | |
|--|--|
| 中文 | **卡卡西** |
| skill | **`kakashi`** |
| 日文 | **カカシ** |

> English: [README.en.md](README.en.md)

### 为什么叫「卡卡西」

名字借自《火影忍者》里的角色**旗木卡卡西**——人称**复制忍者卡卡西**，本事是看见别人的招式就能学、能用。

写作用这个名字，意思一样直白：**装一份别人的文风人格包，再按包写稿**——复制的是笔迹与节奏，不是去当那个人。装一次，反复用；写完还有闸和回执验收，而不是对话框里随口仿一句就算了。

本项目是独立开源工具，**与原作官方无任何关联**；「卡卡西 / 复制忍者」只作意象与昵称，不声称商标或官方授权。

---

## 真实例子 · 改写前 vs 改写后

同一主题：**用约 200 字评价「卡卡西」这个 skill 本身。**  
**改写前** = 普通助手腔说明文（未过人格包）。  
**改写后** = 本仓库 `examples/persona-luxun` 装成的 **鲁迅 demo 人格** 实跑产物（`deliver_ok=true`，汉字 182，身份闸过、机检过、Judge 过；A 保真 0.74 / B brief 0.91）。

### 改写前（普通助手腔）

> 卡卡西是一个很有用的 AI 写作技能。你可以把喜欢的文章风格做成人格包，以后写稿时直接调用，不用每次都把原文贴进对话框。它还提供机器检查和回执，方便确认稿子有没有跑偏。适合需要长期保持固定文风的创作者和团队使用。整体流程清晰，安装一次就能反复写，比普通网页仿写更省事，也更可控。

### 改写后（鲁迅 demo 人格 · 实跑）

> 开源工具卡卡西，说是能装文风人格包，再按包写稿，并出验收回执。装一次人格，往后便可反复调用，不必次次从零捏腔调。
>
> 机器闸卡住格式与禁区，回执把过与不过写明白，亦可复核；比起网页上随口仿写，这里多了一道硬验收。
>
> 只会把原文贴进对话框里聊的，往往聊着便跑腔，热闹一阵就散。空口学腔，终究难交差。
>
> 这里却把人格钉成包，写完还有闸与单可查。冷眼看去，热闹的是仿，认真的是验收，后者才算把「像不像」从嘴上搬到纸面上，少些口头空热闹。

原文档：[`examples/readme-demo/before-plain.md`](examples/readme-demo/before-plain.md) · [`examples/readme-demo/after-luxun.md`](examples/readme-demo/after-luxun.md) · 回执摘要 [`examples/readme-demo/RECEIPT.summary.md`](examples/readme-demo/RECEIPT.summary.md)

> 学的是**笔迹**，不是身份壳。禁止把在世真人商务口吻当「本人」冒充。

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
- `examples/readme-demo` — 上方 README 前后对比的落盘稿

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
