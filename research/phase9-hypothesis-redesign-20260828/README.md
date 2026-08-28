# Phase 9 Hypothesis Redesign

更新日: 2026-08-28
状態: `DRAFT_FOR_DISCUSSION_NOT_PREREGISTERED`

## 目的

Phase 8で棄却された15候補を閾値調整で延命せず、失敗原因を整理したうえで、
独立した経済メカニズムを持つPhase 9候補を作り直す。

このディレクトリは仮説段階の草案であり、まだDiscovery検証を開始していない。
ユーザーとの討論後に候補を修正し、数値仕様、対象集合、期間、Gateを凍結してから検証へ進む。

## 現在の成果物

- `PHASE8_HYPOTHESIS_REVIEW.md`: 旧15候補の失敗原因と、廃止・統合・再設計の判断
- `HYPOTHESIS_PORTFOLIO.md`: Phase 9の15候補を日本語で比較する討論用一覧
- `spec/candidate_registry.draft.json`: 完全な数値条件を含む機械可読草案
- `policy/hypothesis_stage_policy.json`: 仮説段階で許可・禁止する操作
- `sources/PRIMARY_RESEARCH.md`: 新設計の根拠と、論文を短期売買へ外挿しないための注意
- `SESSION_STATE.json`: 現在地と未開封データの状態

## 重要な境界

- `STRAT-PA-002`は`REJECT_FOR_DEVELOPMENT`のまま。再最適化、閾値変更、H4のみ採用、EA化をしない。
- Phase 8の15候補もすべて`REJECT_FOR_DEVELOPMENT`のまま。旧IDを再検証しない。
- Phase 9候補はすべて新IDで、現時点の判定は`UNTESTED_DRAFT`。
- 2019-08-28〜2022-08-28のPhase 8 Discovery結果を、Phase 9の閾値・銘柄・時間足選択に使わない。
- 2025-08-28〜2026-08-28のFinal Holdoutは未開封のまま維持する。
- OOS、Walk Forward、現実的なOANDA MT5コスト検証を通過するまでEA実装を行わない。

## 仮説ポートフォリオ

| 系統 | 件数 | 方向構成 |
|---|---:|---|
| Price Structure | 5 | 継続3、反転2 |
| Liquidity / Volatility | 5 | 継続3、反転2 |
| Relative Value / Regime | 5 | 継続2、相対回帰3 |
| 合計 | 15 | 継続8、反転・相対回帰7 |

## 次の作業

1. 15候補の経済仮説と実装可能性をユーザーと討論する。
2. 重複候補を削除し、必要なら新候補と入れ替える。結果を見て候補を増減しない。
3. Phase 9専用の未使用Discovery期間とデータ可用性を確定する。
4. 候補、期間、universe、matched control、outcome、multiple-testing Gateを凍結する。
5. 凍結コミット後にのみデータ取得とDiscovery検証を開始する。
