# 隔离环 v3.3.1

| 角色 | 做 | 禁 |
|---|---|---|
| Orchestrator（主控 **或** console） | 脚本 + 派 Writer/Judge + 读闸 | 代写终稿；另写一套提示词 |
| 工厂 | sample + rules + qc | 代写终稿 |
| Writer | 只吃 **SPAWN_PROMPT**（内含 WRITE_PROMPT）→ draft | 改 persona；残缺提示 |
| Judge | 只吃 **SPAWN_PROMPT**（内含 JUDGE_PROMPT）→ JUDGE_SCORE.json | 改 draft；只报硬分 |
| Gates | identity / brief / hard / dual_axis / loop_state | 改文风 |

```
hygiene → 截窗 → rules → qc → loop init
  → build_write_prompt → build_agent_handoff(writer)
  → SPAWN_PROMPT 注入 Writer → draft
  → post_write_gates → build_judge_prompt → build_agent_handoff(judge)
  → SPAWN_PROMPT 注入 Judge → dual_axis_gate
  → loop_state record → 过则交付 / 否回炉 ≤5
```

**禁**：`--voice`；硬分单独 PASS；主控/console 手写 draft 冒充流水线；网页端与 skill 两套注入词。
