---
name: magicpen
description: "神笔 / magicpen：可安装文风产线+人格包。Install(原文→persona) / Write(persona+要求→draft+RECEIPT)。触发：神笔、magicpen、神笔马良、文风克隆、人格包、克隆文风、写笔迹。润色→copywriting。"
---

# 神笔 · magicpen · 神笔

> **可安装的文风产线 + 人格包。**  
> 不是「更会模仿的对话框」。学笔迹，不学身份。**风格 ≠ 身份**。  
> 唯一目录：`~/.omp/agent/skills/magicpen`。用户人格库：`~/.omp/magicpen/personas/<id>/`。
>
> **命名**：取自《神笔马良》——画什么成什么；克隆的是笔迹，不是身份。与官方无关联，仅寓意。

## 和网页仿写差在哪

| 网页 AI | 神笔 |
|---|---|
| 每次贴原文 | **Install 一次，Write 多次** |
| 只出一篇字 | **draft + RECEIPT 验收回执** |
| 串角色/掉结构常静默 | 身份硬扫 + brief 机检 + 默认 Judge |
| 无法点名复用 | 人格包可安装、可点名 |

## 两入口（只认这两个）

用户话术：**创建人格** → **写稿**（顺序固定：先有人格包，再写）。  
对内命令名仍是 `run_install` / `run_write`（`--gates-only` 保留 CLI 旗标，界面写「只跑机器硬闸」）。

### 创建人格 · 原文 → 人格包（内部：Install / `run_install`）

范文（I1）**每个会话/人格只有一份** `raw.md`：

1. **自己贴文** 或 **一键网搜**（`run_sample_search_llm` + cliproxy grok-4.5）——只是填入方式不同，**结果都写入同一 raw**；新搜/新贴 = **覆盖**。  
2. 要第二份范文 = **新会话 / 新人格**，禁止双框并存。  
3. 高级：只生成 SPAWN 外置跑，仍落同一 raw。  

密钥：`CLIPROXYAPI_API_KEY` / `MAGICPEN_LLM_KEY` / `OPENAI_API_KEY` / `ANTHROPIC_AUTH_TOKEN`；基址 `MAGICPEN_LLM_BASE` / `CLIPROXY_BASE` / `OPENAI_BASE_URL`（默认 `http://127.0.0.1:8317`）。模型 `MAGICPEN_LLM_MODEL`（默认 grok-4.5）；超时 `MAGICPEN_LLM_TIMEOUT`（默认 300s）；推理档 `MAGICPEN_LLM_REASONING`（如 `high`，可选）。

```bash
pythonw scripts/run_install.py --raw RAW.md --id laocai [--calibrate]
```

产物：`~/.omp/magicpen/personas/<id>/` 下 `sample.md` `rules.md` `metrics.json` `persona.json` + **v3.4** `mind.md` `content_ban.txt`。

### v3.4/v3.5 灵魂层（机检绿 ≠ 像）

| 层 | 作用 |
|---|---|
| **mind.md** | 可迁移「怎么想」：刺激→查证/场面→反差→判断→短收；换题不换脑回路 |
| **content_ban.txt** | 样本事件/专名硬禁（富士山问题）；brief 已写专名豁免 |
| **rules 加权** | P0 灵魂/布局/口气 > P1 节奏 > P2 表层；条数可变，禁 20 条等权假绿 |
| **随机槽** | 每跑 seed 抽开篇/隐喻/收束/中段；禁四篇同构万能稿 |
| **Judge C 轴** | `axis_c_soul≥0.72` 才可 `pass`；缺字段 = 未评 = 失败 |
| **Writer** | 字数不足/中段提纲 → **先 mind 回炉**再加厚（≤4×1.15）；裸 `一、`→`## 一、`；**写后硬清破折号** |
| **section_scene** | 分节文每节须有场面/查证动作（v3.5 机检硬闸） |
| **sample** | **默认注入笔迹样本**；`--no-sample` 仅实验，不作交付默认 |
| **brief** | 长文用 `references/brief-longform-v35.md`：阶段清单+自拟节题，禁焊死船/漆/镜 |

Kill：`pythonw scripts/assert_soul_v34.py` exit0。  
交付前另跑：`assert_magicpen_no_legacy.py`。  
参数锁定与 AB 结论：`references/soul-v34-locked.md`。

### 写稿 · 人格包 + 要求 → 稿 + 回执（内部：Write / `run_write`）

写稿产线（控制台默认 **页内 Grok**；skill 会话可选外置分身）：

```bash
pythonw scripts/run_write.py --persona laocai --brief BRIEF.md --stage prepare
# → WRITE_PROMPT + SPAWN_PROMPT.md + AGENT_HANDOFF.json
# 默认一键写（与控制台 W3 同合同）：
pythonw scripts/run_writer_llm.py --run-dir ~/.omp/magicpen/personas/laocai/runs/rN
# → cliproxy grok-4.5 写 draft.md（密钥 CLIPROXYAPI_API_KEY）
# 高级：外置 Writer 分身仍可整段注入 SPAWN_PROMPT
pythonw scripts/run_write.py --persona laocai --brief BRIEF.md --stage post --run-id rN
pythonw scripts/run_write.py --persona laocai --brief BRIEF.md --stage finalize --run-id rN
```

**注入 SSOT：** `scripts/build_agent_handoff.py`。  
页内 LLM 与外置分身 **同一 WRITE_PROMPT 合同**；禁网页另写一套文风提示。

**交付物（缺一不可）：** `draft.md` + `RECEIPT.md` + `RECEIPT.json`。  
`deliver_ok=false` 也要出回执。

**只跑机器硬闸**（CLI：`--gates-only`，须用户**明文**/界面勾选）：仍跑身份污染 + brief 机检，**跳过评分分身**；RECEIPT 标注降级。适合先通流程，不当正式交稿默认。

## 字数（样本）

硬底 **500** · 硬顶 **3000** · 默认截 **≤2000**。

## 权利

公开材料学写法 → 直接做。  
整篇原文当己作发表 / 冒充在世真人商务 → **拒绝**。

## 人格包

```
~/.omp/magicpen/personas/<id>/
  persona.json
  sample.md
  rules.md            # 加权 P0/P1/P2
  mind.md             # v3.4 思维链
  content_ban.txt     # v3.4 内容禁表
  metrics.json
  identity_ban.txt    # 可选
  runs/rN/ draft RECEIPT GATES JUDGE_* …
```

skill 内 `examples/` 仅 demo（≤3：`laocai` / `luxun`《藤野先生》/ `soseki`）。  
`pythonw scripts/seed_demos.py` 装进 `~/.omp/magicpen/personas/` 后可直接 `--persona luxun` 写稿。  
研究堆在 `archive/`，**不进默认路径**。

## 本机控制台（人手步进 · 与 skill 同合同）

```bash
cd ~/.omp/agent/skills/magicpen/console
pythonw server.py
# http://127.0.0.1:18766/
```

模式顺序（界面左→右）：**创建人格** → **写稿**（禁止再写「装笔」）。

顶栏状态：`✓` 完成 · `→` 等人确认 · 灰=未做。  
**改中间输入级联重置后续步**（改 raw→I2–I5 回未做；改 brief→W2+ 回未做）。  
人手步主按钮文案是「…没问题，下一步」，不是空转的「跑本步」。

| 控制台步 | 用户可见名 | 等价 skill |
|---|---|---|
| I1 | **起名** + 贴范文 / 网搜 | 显示名必填；手贴 raw 或 `run_sample_search_llm`；过闸进 I2 |
| I2 | 可改槽位 + 抽指纹 | **默认新 id**；覆盖须显式勾选。再 `run_install` |
| I3–I5 | 校准 / 体检 / 入库 | `run_install`（可 --calibrate） |
| W2 | 组装提示 | `run_write --stage prepare` → WRITE_PROMPT + SPAWN（高级外置用） |
| W3 | 写正文 | **默认** `run_writer_llm`（cliproxy grok-4.5 写 draft）；高级才复制 SPAWN 外置 |
| W4 | 机器硬闸 | `run_write --stage post` → SPAWN_PROMPT(judge) 或 `--gates-only` |
| W5 | 评分 | **默认** `run_judge_llm`；勾「只跑机器硬闸」跳过 |
| W6 | 回执交付 | `run_write --stage finalize` → RECEIPT；成功时**自动拷一份到桌面** |

页顶流水线图标当前步。说明见 `console/README.md`。

## 主控纪律

1. 禁止手拼 10+ 裸命令冒充产线；走 `run_install` / `run_write`（或控制台点步）。  
2. **禁止主控/控制台手写 draft 冒充 Writer**；写作只交给分身，注入词 = SPAWN_PROMPT。  
3. 默认必须：写后机检 → Judge → dual_axis；身份失败不可交付。  
4. 一人一包；`hygiene` keep-runs 默认 1。  
5. 编排细节：`references/auto-pipeline.md`；隔离：`references/isolation-loop.md`。  
6. 改 console 或 handoff 脚本须两端同改，禁只改网页词。

## 核脚本（facade 已封装）

| 脚本 | 作用 |
|---|---|
| **run_install.py** | Install 入口 |
| **run_write.py** | Write 入口（prepare/post/finalize） |
| **build_agent_handoff.py** | Writer/Judge/**sample_search** SPAWN_PROMPT SSOT |
| clean_sample_text.py | 范文清洗（去壳/压空行） |
| cliproxy_chat.py | 经 cliproxy 调 chat/completions（默认 grok-4.5） |
| run_sample_search_llm.py | I1 一键：SPAWN→Grok→清洗 |
| **run_writer_llm.py** | W3 一键：WRITE_PROMPT→Grok→draft |
| build_receipt.py | RECEIPT |
| style_sensors / cut_train_window / quality_check | 工厂 |
| build_write_prompt / build_judge_prompt | 提示组装 |
| post_write_gates / dual_axis_gate / loop_state | 闸与回环 |
| assert_identity_bleed / assert_content_bleed / check_brief_compliance | 硬检 |
| extract_mind_and_bans | Install 抽 mind+content_ban |
| hygiene_persona / persona_lib | 库与卫生 |
| assert_magicpen_no_legacy / **assert_soul_v34** | Kill 旧名 / 灵魂层接线 |

交付前：

```bash
pythonw scripts/assert_magicpen_no_legacy.py
pythonw scripts/assert_soul_v34.py
```
