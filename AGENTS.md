# Repository Agent Instructions

このリポジトリでPhase 9研究を扱う前に、必ず次を完全に読んでください。

`research/phase9-hypothesis-redesign-20260828/PHASE9_OPERATIONS_GUIDE.md`

## 最優先

- 数値仕様は`spec/candidate_registry.frozen.json`
- データ境界は`spec/data_requirements.frozen.json`
- 許可・禁止は`policy/preregistered_research_policy.json`
- draftを実行しない
- 2019-08-28以降をPhase 9取得workflowから要求しない
- Count-only Gate前にreturn、MFE、MAE、edgeを計算しない
- 旧tmp workflowsを再有効化しない
- raw市場データや秘密情報をcommitしない
- 全Gate前にMT5 EAを実装しない

## サブエージェント

8つの論理役割を使いますが、実際の同時実行上限に従います。主担当だけが最終統合・commit・pushを行い、サブエージェントは原則read-only監査とします。同一ファイルを並列編集しません。

## GitHub

作業開始前にremote mainを確認し、push後にremote head、更新ファイル、Actions runを再確認します。force push、reset --hard、ユーザー変更の破棄は禁止です。
