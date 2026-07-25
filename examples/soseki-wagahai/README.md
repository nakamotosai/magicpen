# 夏目漱石 · 我是猫 · kakashi 人格包

旧 `examples/soseki-zh-voice` 已删除。本目录为 **卡卡西** 流水线重做版。

## 人格包

路径：`personas/persona-soseki-wagahai/`

| 文件 | 说明 |
|---|---|
| sample.md | 截窗后中文（完整段，约 1849 汉字） |
| rules.md | 传感器编译的 20 条一句指令 |
| metrics.json | 硬分旁证 |
| meta.json | 来源与权利说明 |
| runs/ | WRITE_PROMPT / draft |

## 样本权利

- 日文：夏目漱石《吾輩は猫である》青空文库公版
- 中文：据公版日文 **自译** 供笔迹对齐（非胡雪/于雷/刘振瀛等商业全译本镜像）
- 学的是 **句律与旁观讽刺**，不是 cosplay 角色免责

## 重建命令

```bash
python3 scripts/cut_train_window.py --sample examples/soseki-wagahai/raw/wagahai_zh_selftrans.md --out examples/soseki-wagahai/personas/persona-soseki-wagahai/sample.md --target 2000 --min 500 --max 3000 --strategy head
python3 scripts/style_sensors.py --text .../sample.md --rules .../rules.md --metrics .../metrics.json --min-chars 500
python3 scripts/quality_check.py --persona examples/soseki-wagahai/personas/persona-soseki-wagahai
```
