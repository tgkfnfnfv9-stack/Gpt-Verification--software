# Phase 9 仮説ポートフォリオ（事前登録正本）

更新日: 2026-08-29  
状態: `FROZEN_PREREGISTERED`

正式なalpha仮説は11件、独立alphaではないrisk overlayは1件で、confirmatory questionは合計12件です。全件未検証です。

## Formal alpha hypotheses

| 系統 | ID | 名称 | 対象・時間足 | Gate profile |
|---|---|---|---|---|
| Price Structure | PS-202 | Failed 20-Bar Break Reversal | 全12、M15/H1/H4 | BROAD_MULTI_ASSET_3TF |
| Price Structure | PS-203 | Higher-Timeframe Trend Pullback Re-acceleration | 全12、M15/H1/H4 | BROAD_MULTI_ASSET_3TF |
| Price Structure | PS-204 | European Session Range False-Break | FX8＋金銀、M15/H1 | BROAD_MULTI_ASSET_2TF |
| Price Structure | PS-205 | Long-Horizon Trend with Intraday Pullback | 全12、H1/H4 | BROAD_MULTI_ASSET_2TF |
| Liquidity / Volatility | LV-201 | Seasonally Adjusted Participation Shock | 全12、M15/H1/H4 | BROAD_MULTI_ASSET_3TF |
| Liquidity / Volatility | LV-202 | Compressed Balance Release Retest | 全12、M15/H1/H4 | BROAD_MULTI_ASSET_3TF |
| Liquidity / Volatility | LV-203 | Confirmed Climactic Absorption | 全12、M15/H1/H4 | BROAD_MULTI_ASSET_3TF |
| Relative Value / Regime | RR-201 | Cross-Sectional FX Momentum Rank | FX8、H4 | FX_CROSS_SECTION_H4_ONLY |
| Relative Value / Regime | RR-202 | Currency-Basket Residual Reversion | FX8、H1/H4 | FX_NETWORK_2TF |
| Relative Value / Regime | RR-203 | Gold-Silver Dynamic Hedge Residual | 金銀、H4 | TWO_LEG_PAIR_H4_ONLY |
| Relative Value / Regime | RR-204 | Brent-WTI Dynamic Hedge Residual | Brent/WTI、H4 | TWO_LEG_PAIR_H4_ONLY |

## Risk overlay

| ID | 内容 | Primary |
|---|---|---|
| RISK-P9-RO-201 | PS-205のH4 Entryを完全共有し、年率10%target-vol、0.25〜1.50倍でsize調整 | Managedとunit-notionalのDelta episode Sharpe |

## Pretest disposition

| 旧草案 | 処置 |
|---|---|
| PS-201 | 結果未閲覧でLV-202へ統合 |
| LV-204 | 旧VV-104との独立性不足により削除 |
| RR-205 | point-in-time carry data未確保のためDATA_INSUFFICIENT_PRETEST。差し替えなし |
| LV-205 | PS-205とsignal generatorが重複するためrisk overlayへ移動 |

数値Entry、情報時点、control、episode、cost、sample-size、breadth、FDRは `spec/candidate_registry.frozen.json` を正本とします。旧`HYPOTHESIS_PORTFOLIO.md`と`spec/*.draft.json`は討論前の履歴であり、実行に使用しません。
