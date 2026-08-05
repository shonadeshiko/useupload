---
type: project-detail
name: GitHub公開準備 — 何を・どこに・どうやって公開するか
parent: [[projects/ABM事業化/00-事業フレーム]]
status: 提案（Shonadeshikoの判断待ち）
tags: [GitHub, 公開, 安全確認]
created: 2026-08-05
updated: 2026-08-05
---

# GitHub公開準備

> 2026-08-05、Shonadeshiko より「GitHub Desktopを入れたのでこれでアップロードできるか」
> との質問への回答。**GitHub Desktopは使える。ただし公開範囲について1点、
> 先に確認しておくべきことがある。**

---

## 0. 🔴 最初に確認すべきこと — vault全体を公開しない

このvault（`脳みそ`フォルダ）には、ABM事業化プロジェクト以外に、
**客先案件の技術仕様（地下街洪水アラート）・個人の博士出願計画・
研究アセットの棚卸し・MEMORY.mdの個人情報タグ**等、**公開を意図していない内容**が
大量に含まれている。

**GitHub Desktopで「このvaultフォルダをそのままリポジトリとして公開」してしまうと、
これら全てが一緒に公開されてしまう。**

### ✅ 推奨: ABM事業化フォルダだけを別のリポジトリにする

```
公開してよいもの（ABM事業化フォルダの中身）:
  ├─ index.html                     （データは全て公的機関の公開データのみ）
  ├─ 00〜03, 05〜12 (*.md)         （設計・検証の記録）
  ├─ scripts/*.py                  （再現可能なパイプライン）
  └─ _agent_layer_*.json           （実際のOllama実行ログ、公開して問題ない内容）

公開してはいけないもの（vaultの他の部分）:
  ├─ MEMORY.md                     （個人情報・教訓）
  ├─ projects/地下街洪水アラート/    （客先案件の技術仕様）
  ├─ projects/生態系サービス価値-地価相関/ （査読中の研究の生データ・未公開の分析）
  ├─ daily/                        （個人の日次記録）
  └─ decisions/log.md              （意思決定の経緯、社外秘の判断含む）
```

### 実施方法（2つの選択肢）

**選択肢A（推奨・簡単）**: `projects/ABM事業化`フォルダを丸ごとコピーして、
vaultの外（例: デスクトップの別フォルダ）に新しいフォルダを作り、
**そこをGitHub Desktopでリポジトリ化する。**

**選択肢B**: `projects/ABM事業化`フォルダ自体をgitリポジトリのルートにする
（`git init`をこのフォルダの中で実行する）。vault全体はリポジトリ化しない。

→ **どちらでもよいが、「vaultのルートをリポジトリ化しない」ことだけは徹底する。**

---

## 1. GitHub Desktopでの手順（選択肢Aの場合）

1. コピー先フォルダを作る（例: `C:\Users\t1108\Desktop\tama-abm-hackathon`）
2. `projects/ABM事業化`フォルダの中身を全てそこにコピー
3. GitHub Desktopを開く → `File` → `Add local repository`
4. コピー先フォルダを選択 → 「このフォルダはまだGitリポジトリではありません」
   という表示が出るので「Create a repository」を選ぶ
5. リポジトリ名・説明を入力 → `Create Repository`
6. 変更が一覧に表示されるので、コミットメッセージを書いて `Commit to main`
7. `Publish repository` ボタンを押す（Public/Privateを選択。
   ハッカソン提出なら**Public推奨**、審査員が見られるように）

---

## 2. 事前に確認済みの安全性

- ✅ **埋め込みデータの出典はすべて公的機関の公開データ**
  （JAXA・国土数値情報・社人研・国交省告示）。APIキー・個人情報・客先情報は含まれない。
- ✅ **Ollama・WebGPUの接続先はすべて`localhost`**。外部に送信される秘密情報はない。
- 🔴 未確認: `scripts/*.py`のコメント内に記載されている**絶対パス**
  （例: `C:\Users\t1108\OneDrive\Desktop\calc\claudecode\Pricedata\...`）は、
  Shonadeshiko個人のPC環境を示す情報ではあるが、機密情報ではないため公開しても
  実害はないと考えられる。気になる場合は相対パス表記に書き換えることもできる。

---

## 3. タスク

- [ ] [P0|XS] 公開範囲を選択肢A・Bのどちらにするか決める — Shonadeshiko判断待ち
- [ ] [P1|XS] コピー先フォルダの作成・GitHub Desktopでのリポジトリ化（本人作業）
- [ ] [P2|XS] README.mdを新規作成するか検討（現状00-事業フレーム.mdが概要を兼ねているが、
      GitHubのトップページ表示用に短い専用READMEがあると見栄えが良い）

## 関連
- [[projects/ABM事業化/00-事業フレーム]]
- [[projects/ABM事業化/04-流出係数プロトタイプ]]
