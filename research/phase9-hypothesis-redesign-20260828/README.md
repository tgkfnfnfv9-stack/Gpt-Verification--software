# Phase 9 Hypothesis Redesign

更新日: 2026-08-29  
状態: `FROZEN_PREREGISTERED`

最初に [PHASE9_OPERATIONS_GUIDE.md](./PHASE9_OPERATIONS_GUIDE.md) を読みます。全手順、仮説一覧、GitHub取得方法、サブエージェント分担、Gate、禁止事項、更新・引き継ぎ方法の運用正本です。

## 科学仕様の正本

- `spec/candidate_registry.frozen.json`
- `spec/data_requirements.frozen.json`
- `policy/preregistered_research_policy.json`

## 現在地

| 項目 | 状態 |
|---|---|
| Formal alpha | 11 |
| Risk overlay | 1 |
| Confirmatory questions | 12 |
| Phase 9 outcome access | なし |
| 正式なPhase 9データ取得 | 未開始 |
| Provider acquisition | JForex isolated reproducible Build preflight準備済み・実取得はruntime closure/full-QC経路待ち |
| Discovery | 未開始 |
| MT5 EA | 禁止 |

旧tmp workflowによる境界事故が確認されています。`POLICY_INCIDENT_20260829.md`を参照してください。2022〜2026年は後続splitとしての有効性再監査が必要です。

公開endpoint取得は`PROVIDER_ACQUISITION_BLOCKER.md`の3件のP0により廃止しました。代わりに`JFOREX_SOURCE_CHANNEL_AMENDMENT.md`で、公式認証JForex Tester API、4つの固定取得run、H1の一律2019年8月除外を結果未閲覧で凍結しています。市場price fileはまだ0件です。次はcredential・price stepを持たないisolated reproducible Build preflightで、依存inventory、runtime identity、online 1回＋offline 2回のJAR SHA一致を採取します。

`HYPOTHESIS_PORTFOLIO.md`、`spec/*.draft.json`、`policy/hypothesis_stage_policy.json`は履歴であり、実行に使用しません。
