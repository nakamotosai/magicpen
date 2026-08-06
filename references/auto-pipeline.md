# 全自动流水线 · magicpen v3.3.1（产品态）

> 用户可见：**创建人格** → **写稿**（禁称「装笔」）。  
> 对内命令：`run_install` / `run_write`。本文件是 facade 内部合同。  
> **控制台 = 同合同的人机步进面**，不是第二套产线。

## 入口

| 用户话 | 命令 | 作用 |
|---|---|---|
| 创建人格 | `run_install.py --raw --id [--calibrate]` | 原文→`~/.omp/magicpen/personas/<id>` |
| 贴/搜范文 | 手贴 raw；或 `run_sample_search_llm.py`（SPAWN+cliproxy grok-4.5+清洗）；高级 `build_agent_handoff --role sample_search` | I1 样本进会话 `raw.md` |
| 写稿 | `run_write.py --persona --brief --stage prepare\|post\|finalize` | 写稿编排 + 闸 + RECEIPT |
| （内） | `build_agent_handoff.py --role writer\|judge\|sample_search` | 分身注入包 SSOT |

## 写稿分阶段（AGENT_HANDOFF）

```
prepare  → WRITE_PROMPT + SPAWN_PROMPT(writer) + AGENT_HANDOFF
           【默认】run_writer_llm（cliproxy grok-4.5）→ draft.md
           【高级】整段 SPAWN 外置 Writer 分身
post     → GATES + JUDGE_PROMPT + SPAWN_PROMPT(judge)  或「只跑机器硬闸」合成
           【停】整段 SPAWN → Judge 或跳过
finalize → dual_axis + RECEIPT + loop + hygiene     【交稿】
```

页内 LLM 与外置分身 **同一 WRITE_PROMPT**；禁网页另写文风提示。  
run 目录：

- `WRITE_PROMPT.md`（合同 SSOT）
- `SPAWN_PROMPT.md`（外置分身用；页内 LLM 用 `SPAWN_PROMPT_RUNTIME_WRITER.md`）
- `AGENT_HANDOFF.json` / `ORCHESTRATE.json`

## 默认闸

`post_write_gates`（身份污染 + brief 机检 + 硬分旁证）→ 评分分身 → `dual_axis_gate` → `build_receipt`。

- 身份失败 / gates 失败 → `deliver_ok=false`，仍出 RECEIPT  
- **只跑机器硬闸**（CLI `--gates-only`）：用户明文/界面勾选；仍跑硬闸，跳过评分分身；RECEIPT 标降级

## 角色

| 角色 | 做 | 禁 |
|---|---|---|
| Orchestrator（主控或 console） | 调 facade、派分身、读 RECEIPT | 代写 draft |
| Writer | 只吃 SPAWN_PROMPT → draft.md | 改 persona；残缺提示 |
| Judge | 只吃 SPAWN_PROMPT → JUDGE_SCORE.json | 改 draft；只报硬分 |
| Gates | identity / brief / hard / dual_axis / loop | 改文风 |

## 控制台状态机（与 skill 同合同）

- 人手步（I1/W1/W3/W5）：主按钮 = **过闸前进**，不是空跑脚本  
- 脚本步：主按钮才真跑 facade  
- **级联重置**：改 raw / brief / draft / judge 输入 → `invalidate_after` 把后续 step 打回 `idle`  
- 顶栏：`✓` done · `→` await_gate · 灰 idle · `…` running · `!` failed  
- **创建人格槽位**：默认全新 `new_persona_id`；**禁止**静默复用顶栏 `persona_id`（曾误写 soseki）。覆盖须 `install_overwrite=true` 且显式选目标；撞库硬拒。  
- **切段**：`style_sensors.split_paras` 空行优先，中文单换行散文回退为行≈段，避免 para_count=1 毒 rules。  

## 卫生

- 人格库外置；examples ≤3 demo  
- `hygiene_persona --keep-runs 1`  
- `archive/` 研究堆不进默认路径  

