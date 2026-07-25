# 写稿路径 v3.3.1

## Writer 路径

加载 **persona** → 拼 WRITE_PROMPT → **SPAWN_PROMPT**：

1. `sample.md` 原文全文（**仅笔迹**；非角色库）  
2. **`rules.md` 全文**（约 20 条一句指令）  
3. 新文主题 + 用户条件（人称/事实只听这里）  
4. `build_agent_handoff --role writer` → 分身整段注入词  

铁律含 **风格≠身份**。

```bash
pythonw scripts/run_write.py --persona ID --brief brief.md --stage prepare
# 或底层：
pythonw scripts/build_write_prompt.py --persona P --brief brief.md --out P/runs/r1/WRITE_PROMPT.md
pythonw scripts/build_agent_handoff.py --role writer --prompt P/runs/r1/WRITE_PROMPT.md --out-dir P/runs/r1
# → 把 SPAWN_PROMPT.md 整段注入 Writer 分身；只写 draft.md
```

## 写后路径（全自动必跑）

```bash
pythonw scripts/run_write.py --persona P --brief brief.md --stage post --run-id rN
# 底层等价：
pythonw scripts/post_write_gates.py --persona P --draft P/runs/rN/draft.md --brief brief.md --out P/runs/rN/GATES.json
pythonw scripts/build_judge_prompt.py --persona P --draft ... --brief ... --gates ... --out P/runs/rN/JUDGE_PROMPT.md
pythonw scripts/build_agent_handoff.py --role judge --prompt P/runs/rN/JUDGE_PROMPT.md --out-dir P/runs/rN
# Judge 分身只吃 SPAWN_PROMPT → JUDGE_SCORE.json
pythonw scripts/dual_axis_gate.py --judge P/runs/rN/JUDGE_SCORE.json --gates P/runs/rN/GATES.json --out P/runs/rN/DELIVER.json
```

无 `--voice`。无 anchor.json 主路径。编排见 `auto-pipeline.md`。  
console W3/W5 与上表同一 SPAWN_PROMPT，禁止网页另写注入词。
