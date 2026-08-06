# 神笔 v3.4 灵魂层 · 锁定参数（2026-07-26 AB）

> AB 目录：`~/.omp/magicpen/personas/laocai/runs/ab-soul-20260726/`  
> 结论：**机检绿 ≠ 像**；交付必须 `axis_c_soul≥0.72` + content_bleed 过 + identity 过。

## 控制变量结果（laocai · 高市人生评）

| 组 | 变量 | C soul | deliver | 读感 |
|---|---|---|---|---|
| A2 | 无 mind；brief 焊死船/漆/镜节题 | ~0.48–0.50 | ❌ | 通用政论/评传 |
| B2 | 有 mind；仍焊死船/漆/镜节题 | ~0.63–0.68 | ❌ | 口语壳+履历提纲 |
| B3 | mind + **去模板 brief**（自拟节题） | ~0.70–0.74 | ✅/边缘 | 开篇像老蔡，中段仍易提纲化 |
| C3 | mind + 去模板 brief + **另一 seed** | **0.74** | ✅ | 开篇/节题与 B3 不同，随机槽生效 |

## 锁定（生产默认）

1. **Install 必产** `mind.md` + `content_ban.txt`（`extract_mind_and_bans`）。
2. **rules 加权** P0>P1>P2（`style_sensors` 0.6.0-soul），禁 20 条等权。
3. **Writer**：mind 置顶；sample 仅笔迹；content_ban 硬禁；**随机槽**（opener/metaphor/close/aside）；字数不足先 mind 回炉再加厚≤4×1.15；裸 `一、`→`## 一、`；**终稿 `strip_em_dashes`**。
4. **Brief 纪律（关键）**：长文分节时 **禁止焊死万能隐喻节题**（船/漆/镜/账本…）；给阶段清单 + 允许自拟 `## 一、` 标题；开篇强制刺激→查证→反差。
5. **Judge 三轴**：A≥0.7 B≥0.7 **C≥0.72**；缺 C 字段 = 失败；机检汉字 ok 时禁止幻觉「字数不足」拖垮 B。
6. **Gates**：identity + content_bleed + brief_compliance + **section_scene**；dual_axis 须 content_ok + section_ok + C。
7. **Kill**：`assert_soul_v34.py` + `assert_magicpen_no_legacy.py`。

## v3.5 多 seed 实测（laocai · 2026-07-26）

| 轮 | deliver | 备注 |
|---|---|---|
| 首跑 S1–S3 | 0 | 全 ~1690 字机检挂；C 0.69–0.75 |
| rescue 加厚 | **S2 C=0.74** | S1/S3 字数够但 C 掉 |
| mind_fix | **S3 C=0.75** | S2 二评 C 抖到 0.68；S4 破折号 3.7/1k 挂 |
| **round2** | **4/5 strict** | S2 C0.75 · S3 C0.74 · S5 C0.74 · S6 C0.76；S1 短稿失败；opener/H2 全互异 |
| 结论 | 满意门槛达成 | Writer 硬清破折 + 1.15×扩写 + rewrite_directives 回炉 + 新 seed |

证据：`personas/laocai/runs/ab-v35-20260726/SUMMARY_ROUND2.json`

## 仍未彻底消灭

- 中段履历/特稿感：长结构 brief 仍会把 mind 压成「六节评传」。
- 注水扩写可能略伤 C：优先 **mind/rewrite_directives 定向回炉**，其次加厚。
- Judge 分数有波动：以 dual_axis + 机检硬闸为准，C 边界稿可二评；**勿把单次 0.74 当稳绿**。

## 随机性证明

同 brief_soul、不同 seed：
- B3 opener：`别只在热搜里给自己加戏` / 节题「先学会输…」
- C3 opener：`群里突然刷屏` / 节题「先输再进门…」
二者 H2 全集不同 → 随机槽+自拟节题有效。

## 有 sample 笔迹 vs 只参数（2026-07-26）

同 `brief_soul`、同 seed `ab-c3-soul-s2`：

| 组 | 注入 | han | A | B | C | deliver |
|---|---|---|---|---|---|---|
| C3 | mind+rules+**sample 笔迹**+ban | 2206 | 0.79 | 0.90 | **0.74** | ✅ |
| D | mind+rules+**metrics 数值**+ban（`--no-sample`） | 2055 | 0.74 | 0.90 | **0.64** | ❌ |

结论：
- **只参数能过结构/字数（补齐后）**，但灵魂轴掉约 0.10，读感更像「按说明书写的口语模板」。
- 无 sample 时易 **过拟合空行/单句成段**（D 空行比明显高于 C3），却缺真实口气纹理。
- **生产默认仍注入 sample（仅笔迹）**；`--no-sample` 仅实验/对照，不作默认交付。
- 脚本：`build_write_prompt.py --no-sample`；对照 JSON：`personas/laocai/runs/ab-soul-20260726/AB_PARAMS_ONLY_vs_SAMPLE.json`。
