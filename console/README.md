# 卡卡西本机控制台

本机网页步进操作 **创建人格 / 写稿**（内部仍是 Install / Write facade）。  
与 skill 本体 **同一套 facade + 同一套 SPAWN_PROMPT**。  
不新造仿写算法；**不代替 Writer/Judge 分身写正文**。

界面词：**创建人格**（不要写「装笔」）→ **写稿**。  
「只跑机器硬闸」= CLI `--gates-only`：跳过评分分身，回执标降级。

## 启动

```bash
cd ~/.claude/skills/kakashi/console
pythonw server.py
```

http://127.0.0.1:18766/

顶栏精简：模式切换 · 人格下拉（写稿用）· 新会话 · 跑本步。硬闸勾选在底栏（仅写稿）。流水线只留步骤珠，无图例墙。

## 与 skill 等价表

| 控制台 | 用户可见 | skill / 脚本 | 分身 |
|---|---|---|---|
| I1 | 贴范文 / 一键网搜 | 手贴；或 `run_sample_search_llm`（cliproxy grok-4.5 写 raw+清洗） | 默认网页内直连模型；高级才外置 SPAWN |
| I2–I5 | 创建人格后续 | `run_install` | 无（工厂脚本） |
| W2 | 组装提示 | `run_write --stage prepare` | 产出 WRITE_PROMPT（+高级 SPAWN） |
| W3 | 写正文 | **默认** `run_writer_llm`（cliproxy grok-4.5） | 写 `draft.md`；高级才外置 SPAWN |
| W4 | 机器硬闸 | `run_write --stage post` | 产出 Judge 注入词；或「只跑机器硬闸」 |
| W5 | 评分 | **默认** `run_judge_llm`（cliproxy grok） | 人话成绩单给用户看；`JUDGE_SCORE.json` 给机器出回执；高级才露 JSON |
| W6 | 回执交付 | `run_write --stage finalize` | 出回执并**自动拷一份正文到桌面**；不再依赖打开文件夹 |

注入词 SSOT：`scripts/build_agent_handoff.py`（skill 与 console 共用）。

## 写稿手操

1. **选人格**：自动恢复该包最新 `runs/rN`（brief/draft/闸/回执都在）。下拉旁可看历史次数。  
2. 正文区上方 **历史条**：切换 run · 打开 · 全新写 · 从本步清 · 全部清（只动本会话进度，磁盘 run 默认保留）。  
3. W1 写要求 → 保存 → 下一步  
4. W2 **组装提示**  
5. W3 **一键写正文（Grok）** → 可改 → 下一步  
6. W4 硬闸 → W5 **一键评分** → 出回执时正文**自动放到桌面**（库内 runs 仍保留）  




## 创建人格手操

1. I1 **最上方先起名**（显示名必填；id 可空）。  
2. 贴/搜 **一份范文** → **「范文没问题，下一步」**（没起名会拦）。  
3. I2 点「跑创建人格」。默认**全新槽**；覆盖须勾选。  
4. **创建完成后**：起名框收成摘要；顶栏下拉**自动选中**新人设；可点「用它写稿」。  


## 状态与级联

- 顶栏圆点：`✓` 完成 · `→` 等人确认 · `…` 跑着 · 灰字未做 · `!` 失败  
- **改中间输入会重置后面步骤**（如改范文 → I2–I5 回未做；改 brief → W2 以后回未做）  



## 目录

```
console/
  server.py          # 编排 run_* 只
  static/
  runs/<session>/state.json
```

run 产物在人格包：`~/.claude/kakashi/personas/<id>/runs/rN/`  
含 `SPAWN_PROMPT.md` `AGENT_HANDOFF.json` `WRITE_PROMPT.md` `draft.md` …

## 边界

- 默认 127.0.0.1  
- 路径沙箱：人格库 / examples / console runs / scripts  
- 改注入词只改 `build_agent_handoff.py` / `build_*_prompt.py`，禁只在网页里硬编码  
- static 用 classic script  
