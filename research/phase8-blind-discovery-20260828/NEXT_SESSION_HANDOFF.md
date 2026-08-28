# Phase 8 最終引き継ぎ

更新日: 2026-08-28

## 確定事項

- STRAT-PA-002: REJECT_FOR_DEVELOPMENT
- Phase 8の新規15候補: 全件REJECT_FOR_DEVELOPMENT
- WATCH: 0
- DEVELOPMENT: 0
- 正式検証した独立仮説: 合計16
- Final Holdout（2025-08-28〜2026-08-28）: 未取得・未評価
- MT5 EA実装: 禁止継続

## 最後の候補

STRAT-VV-104は全銘柄・M15/H1/H4を同一UTC日×方向episodeへ統合して最終監査した。

- Matched signals: 4,968
- 統合episodes: 1,618
- Edge: +0.2490 ATR
- 95% CI: [-0.0255, 0.5194]
- BH-FDR: 0.5430
- H4 Edge: -0.0226 ATR
- 12時間Signal Return: -0.3082 ATR
- 最終判定: REJECT_FOR_DEVELOPMENT

失敗GateはCI下限、BH-FDR、正の時間足比率。H4を除外した採用、閾値変更、再最適化、
同じDiscoveryデータでの追加試行は禁止する。

## 次に許可される作業

Phase 9として、PA-002、Liquidity Sweep、Phase 8候補を答えとして与えない新しい独立仮説を
Outcome閲覧前に登録する。Development・OOS・Final Holdoutへ進める既存候補はない。
