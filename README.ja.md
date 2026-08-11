<div align="center">

**🌐 作者 [Sai](https://saaaai.com) · 個人サイト [saaaai.com](https://saaaai.com)** — AI ワークフローとオープンソース

**[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md)**

</div>

<p align="center">
  <img src="assets/readme/hero.svg" alt="神笔 · magicpen：インストール可能な文体パイプライン + ペルソナパック" width="100%">
</p>

# 神笔 · magicpen · 神笔

**インストール可能な文体パイプライン + ペルソナパック。**  
学ぶのは**筆跡**であり、アイデンティティではない。**文体 ≠ アイデンティティ**。Install は一度、Write は何度でも。納品には `draft` + `RECEIPT` が必要。

| | |
|--|--|
| 中国語 | **神笔** |
| skill 名 | **`magicpen`** |
| 日本語 | **神笔** |

### 「神笔」の由来

名前の由来は**神笔馬良（シェンビー・マーリャン）**——馬良は神笔を手に入れ、描いたものがすべて本物になるという話。執筆にこのイメージを借りた：**誰かの文体をペルソナパックとして取り込み、以後はそのパックで「描けばその通りに書ける」**——クローンするのは筆跡とリズムであって、その人になることではない。一度取り込めば繰り返し使える。書き終わればゲートとレシートで検収まであり、ダイアログで一句適当に真似るだけではない。

本プロジェクトは独立したオープンソースツール。「神笔」は「書けば何でも形になる」という寓意であり、原作の登場人物や商標とは無関係。

---

## 実例 · 書き換え前 vs 書き換え後

同じブリーフ：**約 200 字で「神笔」という skill そのものを評価する。**  
**書き換え前** = 普通のアシスタント口調の説明文（ペルソナパック未使用）。  
**書き換え後** = 本リポジトリの `examples/persona-luxun` で取り込んだ **魯迅デモ人格** の実走行成果物（`deliver_ok=true`、漢字 182、アイデンティティ・ゲート・Judge すべて通過；A 忠実度 0.74 / B brief 0.91）。

### 書き換え前（普通のアシスタント口調）

> 神笔是一个很有用的 AI 写作技能。你可以把喜欢的文章风格做成人格包，以后写稿时直接调用，不用每次都把原文贴进对话框。它还提供机器检查和回执，方便确认稿子有没有跑偏。适合需要长期保持固定文风的创作者和团队使用。整体流程清晰，安装一次就能反复写，比普通网页仿写更省事，也更可控。

### 書き換え後（魯迅デモ人格 · 実走行）

> 开源工具神笔，说是能装文风人格包，再按包写稿，并出验收回执。装一次人格，往后便可反复调用，不必次次从零捏腔调。
>
> 机器闸卡住格式与禁区，回执把过与不过写明白，亦可复核；比起网页上随口仿写，这里多了一道硬验收。
>
> 只会把原文贴进对话框里聊的，往往聊着便跑腔，热闹一阵就散。空口学腔，终究难交差。
>
> 这里却把人格钉成包，写完还有闸与单可查。冷眼看去，热闹的是仿，认真的是验收，后者才算把「像不像」从嘴上搬到纸面上，少些口头空热闹。

元ドキュメント：[`examples/readme-demo/before-plain.md`](examples/readme-demo/before-plain.md) · [`examples/readme-demo/after-luxun.md`](examples/readme-demo/after-luxun.md) · レシート要約 [`examples/readme-demo/RECEIPT.summary.md`](examples/readme-demo/RECEIPT.summary.md)

> 学ぶのは**筆跡**であって、アイデンティティの外殻ではない。存命の実在人物のビジネス口調を「本人」として名乗ることは禁止。

---

## ウェブの口真似チャットとの違い

| ウェブ AI | 神笔 |
|---|---|
| 毎回原文を貼る | **Install 一度、Write 何度でも** |
| 文字の塊をひとつ出すだけ | **draft + RECEIPT 検収レシート** |
| ロール崩れ・構造崩れが黙って起きる | アイデンティティ検査 + brief 機検 + 既定スコア |
| 名前で再利用できない | ペルソナパックをインストール・指名可能 |

---

## インストール

```bash
git clone https://github.com/nakamotosai/magicpen
```

スキルディレクトリ名は **`magicpen`** である必要がある：

| ホスト | パス |
|------|------|
| omp（本機メインホスト） | `~/.omp/agent/skills/magicpen` |
| Claude Code | `~/.claude/skills/magicpen` |
| Codex | `~/.codex/skills/magicpen` |
| 本プロジェクトのみ | `.claude/skills/magicpen` |

ペルソナライブラリ（既定、**本リポジトリ外**）：`~/.omp/magicpen/personas/<id>/`。

---

## 2つの入口

ユーザー話法：**ペルソナ作成** → **執筆**（先にパック、それから執筆）。

### ペルソナ作成 · 原文 → ペルソナパック

```bash
pythonw scripts/run_install.py --raw RAW.md --id mypen --calibrate
```

成果物：`persona.json` `sample.md` `rules.md` `metrics.json`。

### 執筆 · ペルソナパック + 要求 → 原稿 + レシート

```bash
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage prepare
# 既定は本文を一発生成（OpenAI 互換 chat、下記参照）
pythonw scripts/run_writer_llm.py --run-dir ~/.omp/magicpen/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage post --run-id rN
pythonw scripts/run_judge_llm.py --run-dir ~/.omp/magicpen/personas/mypen/runs/rN
pythonw scripts/run_write.py --persona mypen --brief BRIEF.md --stage finalize --run-id rN
```

**納品物（どれも欠かせない）：** `draft.md` + `RECEIPT.md` + `RECEIPT.json`。  
`deliver_ok=false` でもレシートは出す。

---

## 本機コンソール（手動ステップ実行）

```bash
cd ~/.omp/agent/skills/magicpen/console
pythonw server.py
# http://127.0.0.1:18766/
```

skill と**同じ** `run_install` / `run_write` / 注入語。  
W3/W5 は既定でページ内 LLM；W6 でレシート成功時は本文の**コピーをデスクトップに自動保存**（ライブラリ内 `runs/` には残る）。

---

## LLM 環境変数

ページ内の本文執筆 / スコアリング / サンプル検索は OpenAI 互換 `chat/completions`：

| 変数 | 役割 |
|------|------|
| `CLIPROXYAPI_API_KEY` か `MAGICPEN_LLM_KEY` か `OPENAI_API_KEY` | API キー（必須） |
| `MAGICPEN_LLM_BASE` か `CLIPROXY_BASE` か `OPENAI_BASE_URL` | ベース URL（既定 `http://127.0.0.1:8317`） |
| `MAGICPEN_LLM_MODEL` | モデル（例 `grok-4.5`；env で明示指定必須、既定なし） |

キーは読み取り専用の環境変数であり、リポジトリに書き込まない。

---

## プリセット Demo（取り込めばすぐ書ける）

リポジトリには **3 セット** のすぐ使えるペルソナパック例が付属（`examples/`）。本機ライブラリに取り込めば、コンソールのドロップダウンでも `--persona` でも指名できる：

| 本機 id | 表示名 | サンプル | パス |
|---------|--------|----------|------|
| `laocai` | 老蔡 | 口語・空行の指紋 | `examples/persona-laocai/` |
| `luxun` | 魯迅・藤野先生 | 『藤野先生』（パブリックドメイン） | `examples/persona-luxun/` |
| `soseki` | 夏目漱石・吾輩は猫の質感 | 長段落の冷ややかな皮肉 | `examples/soseki-wagahai/` |

```bash
# 一発で ~/.omp/magicpen/personas/ に取り込む（存在すればスキップ；--force はサンプルを上書きし runs は消さない）
pythonw scripts/seed_demos.py

# 魯迅・藤野先生で直接執筆
pythonw scripts/run_write.py --persona luxun --brief BRIEF.md --stage prepare
```

`examples/readme-demo/` は README の書き換え前後比較用の成果物であり、4 つ目のペルソナではない。

---

## 契約全文

[SKILL.md](SKILL.md) 参照。オーケストレーション：`references/auto-pipeline.md`。

自己検査：

```bash
pythonw scripts/assert_magicpen_no_legacy.py
pythonw scripts/assert_public_surface.py
```

---

## 権利

公開資料から書き方を学ぶ → 可。  
原文全体を自分の作品として発表 / 存命の実在人物になりすましてビジネス → **拒否**。

---

## ライセンス

MIT · [LICENSE](LICENSE)
