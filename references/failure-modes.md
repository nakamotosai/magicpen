# 失败模式 v3.3

| 触发 | 一线 |
|---|---|
| 手拼 10+ 命令 | 改 `run_install` / `run_write` |
| 只交 draft 无 RECEIPT | **未交付**；跑 finalize |
| 还用 `--voice` | 改 `--persona` |
| 缺 rules.md | `run_install` 或 sensors |
| sample 超 3000 / 不足 500 | cut / 补字 |
| 短行原文 | quality_check **不**硬杀；`--calibrate` 或手改 rules |
| 硬分单独定生死 | **禁止**；dual_axis + RECEIPT |
| 身份串味 | `assert_identity_bleed`；回炉 |
| brief 结构未满足 | `check_brief_compliance` |
| 回环 >5 | loop_state exhausted |
| 默认跳 Judge | 仅 `--gates-only` + 用户明文 + RECEIPT 降级标 |
| 研究堆进 live | 只认 `examples/`≤3 demo；其余 `archive/` |
| Judge 缺 JSON | finalize 失败 `judge_missing` |
