# Phase 9 Hypothesis Redesign

更新日: 2026-08-29  
状態: `FROZEN_PREREGISTERED`

Phase 8の15候補とPA-002は全件`REJECT_FOR_DEVELOPMENT`です。Phase 9では旧閾値を再最適化せず、結果未閲覧の討論で正式alpha 11件とrisk overlay 1件を事前登録しました。

## 実行正本

- `HYPOTHESIS_PORTFOLIO_FINAL.md`
- `DESIGN_DECISIONS.md`
- `spec/candidate_registry.frozen.json`
- `spec/data_requirements.frozen.json`
- `policy/preregistered_research_policy.json`
- `DATA_REQUIREMENTS.md`
- `SESSION_STATE.json`

`HYPOTHESIS_PORTFOLIO.md`、`spec/*.draft.json`、`policy/hypothesis_stage_policy.json`は2026-08-28時点の討論用草案で、実行には使用しません。

## 現在地

| 項目 | 状態 |
|---|---|
| Formal alpha hypotheses | 11 |
| Risk overlay study | 1 |
| Confirmatory questions | 12 |
| Phase 9 outcome access | なし |
| データ取得 | 未開始 |
| Discovery | 未開始 |
| Development / OOS / Final Holdout | 未取得・未開封 |
| MT5 EA | 禁止 |

次は凍結コミットを基準に、2013-01-01以上2019-08-28未満だけのデータavailability確認・取得、品質Gate、count-only Gateを行います。return計算はcount-only Gate通過後です。
